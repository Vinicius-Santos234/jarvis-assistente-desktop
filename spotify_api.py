"""
Spotify Web API para o Jarvis (v0.4.1) - play direto e controle do player.

Fluxo OAuth "Authorization Code + PKCE": nao precisa de client secret,
so do Client ID de um app criado em https://developer.spotify.com/dashboard
com o Redirect URI http://127.0.0.1:8917/callback.

Uso:
  1. Cole o Client ID em config.json -> "spotify" -> "client_id"
  2. Rode "Autorizar Spotify.bat" UMA vez (abre o navegador, voce autoriza)
  3. Pronto: o token fica em spotify_token.json e se renova sozinho

Dar play/pausar/pular exige conta Premium (regra do Spotify). Sem
configurar, o Jarvis continua no comportamento antigo (abre a busca).
"""

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TOKEN_PATH = BASE_DIR / "spotify_token.json"

REDIRECT_URI = "http://127.0.0.1:8917/callback"
PORTA_CALLBACK = 8917
ESCOPOS = "user-modify-playback-state user-read-playback-state"

TIPOS = {"musica": "track", "artista": "artist", "album": "album", "playlist": "playlist"}


class SpotifyErro(Exception):
    """Falha com mensagem pronta para o Jarvis falar."""


def _config():
    with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
        return json.load(f).get("spotify", {})


def configurado():
    cfg = _config()
    return bool(cfg.get("ativo", False)) and bool(cfg.get("client_id", "").strip())


# ---------- OAuth PKCE ----------

def autorizar():
    """Fluxo unico de autorizacao: navegador + servidor local para o callback."""
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer

    client_id = _config().get("client_id", "").strip()
    if not client_id:
        raise SpotifyErro("client_id vazio no config.json (secao 'spotify')")

    verificador = secrets.token_urlsafe(64)[:64]
    desafio = base64.urlsafe_b64encode(
        hashlib.sha256(verificador.encode("ascii")).digest()).decode("ascii").rstrip("=")

    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "code_challenge_method": "S256",
        "code_challenge": desafio,
        "scope": ESCOPOS,
    })

    codigo = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            codigo["code"] = qs.get("code", [None])[0]
            codigo["error"] = qs.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>Jarvis autorizado no Spotify! Pode fechar esta aba.</h2>"
                             .encode("utf-8"))

        def log_message(self, *a):
            pass

    servidor = HTTPServer(("127.0.0.1", PORTA_CALLBACK), Callback)
    print("Abrindo o navegador para autorizar o Spotify...")
    webbrowser.open(url)
    servidor.timeout = 180
    servidor.handle_request()  # espera UM callback
    servidor.server_close()

    if not codigo.get("code"):
        raise SpotifyErro(f"autorizacao negada ou expirada ({codigo.get('error')})")

    tokens = _post_token({
        "grant_type": "authorization_code",
        "code": codigo["code"],
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verificador,
    })
    _salvar_tokens(tokens)
    print("Autorizado! Token salvo em", TOKEN_PATH.name)


def _post_token(campos):
    dados = urllib.parse.urlencode(campos).encode("ascii")
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token", data=dados,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", errors="ignore")[:200]
        raise SpotifyErro(f"falha ao obter token ({e.code}): {corpo}")


def _salvar_tokens(tokens):
    antigo = {}
    if TOKEN_PATH.is_file():
        antigo = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    dados = {
        "access_token": tokens["access_token"],
        # o refresh do PKCE pode devolver um refresh_token novo; senao mantem o antigo
        "refresh_token": tokens.get("refresh_token") or antigo.get("refresh_token"),
        "expira_em": time.time() + int(tokens.get("expires_in", 3600)) - 60,
    }
    TOKEN_PATH.write_text(json.dumps(dados, indent=2), encoding="utf-8")
    return dados


def _obter_token():
    if not TOKEN_PATH.is_file():
        raise SpotifyErro('nao autorizado ainda - rode o "Autorizar Spotify.bat"')
    dados = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    if time.time() < dados.get("expira_em", 0):
        return dados["access_token"]
    tokens = _post_token({
        "grant_type": "refresh_token",
        "refresh_token": dados["refresh_token"],
        "client_id": _config().get("client_id", "").strip(),
    })
    return _salvar_tokens(tokens)["access_token"]


# ---------- chamadas a API ----------

def _req(metodo, caminho, token, corpo=None):
    """Chamada a api.spotify.com; devolve (status, json|None).

    status None = a RESPOSTA se perdeu na rede (timeout/queda). O comando
    pode MUITO BEM ter sido executado pelo Spotify - quem chama decide se
    confere o estado do player antes de declarar falha (era a causa do
    Jarvis tocar a musica e responder como se tivesse falhado).
    """
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(
        "https://api.spotify.com/v1" + caminho, data=dados, method=metodo,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            texto = resp.read().decode("utf-8")
            return resp.status, (json.loads(texto) if texto else None)
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", errors="ignore")
        try:
            return e.code, json.loads(texto)
        except json.JSONDecodeError:
            return e.code, {"error": {"message": texto[:200]}}
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, None


def _buscar(token, busca, tipo_api):
    q = urllib.parse.urlencode({"q": busca, "type": tipo_api, "limit": 1})
    status, dados = _req("GET", f"/search?{q}", token)
    if status != 200:
        raise SpotifyErro(f"busca falhou ({status})")
    itens = dados.get(tipo_api + "s", {}).get("items", [])
    if not itens:
        raise SpotifyErro(f"nao achei '{busca}' no Spotify")
    item = itens[0]
    nome = item.get("name", busca)
    artistas = ", ".join(a["name"] for a in item.get("artists", [])) if item.get("artists") else ""
    return item["uri"], nome, artistas


def _dispositivo(token):
    """Devolve o id de um dispositivo; abre o app do Spotify se nao houver."""
    status, dados = _req("GET", "/me/player/devices", token)
    if status == 200 and dados.get("devices"):
        ativos = [d for d in dados["devices"] if d.get("is_active")]
        return (ativos or dados["devices"])[0]["id"]

    # nenhum dispositivo: abre o Spotify e espera ele aparecer
    try:
        os.startfile("spotify:")  # type: ignore[attr-defined]
    except OSError:
        raise SpotifyErro("Spotify nao instalado")
    for _ in range(15):  # ~12 s
        time.sleep(0.8)
        status, dados = _req("GET", "/me/player/devices", token)
        if status == 200 and dados.get("devices"):
            return dados["devices"][0]["id"]
    raise SpotifyErro("abri o Spotify, mas nenhum dispositivo apareceu - tente de novo")


def _tocando_agora(token):
    """(uri_da_faixa, uri_do_contexto, is_playing) do player; Nones se nada."""
    status, dados = _req("GET", "/me/player/currently-playing", token)
    if status != 200 or not dados:
        return None, None, None
    item = dados.get("item") or {}
    contexto = (dados.get("context") or {}).get("uri")
    return item.get("uri"), contexto, dados.get("is_playing")


def tocar(busca, tipo="musica"):
    """Busca e DA PLAY direto. Devolve a frase de resultado para o Jarvis."""
    token = _obter_token()
    tipo_api = TIPOS.get(tipo, "track")
    uri, nome, artistas = _buscar(token, busca, tipo_api)
    device = _dispositivo(token)

    corpo = {"uris": [uri]} if tipo_api == "track" else {"context_uri": uri}
    status, dados = _req("PUT", f"/me/player/play?device_id={device}", token, corpo)
    de = f" de {artistas}" if artistas and tipo_api == "track" else ""
    if status in (200, 202, 204):
        return f"Tocando {nome}{de} no Spotify."
    if status is None:
        # resposta perdida na rede: confere se o play aconteceu mesmo
        # antes de declarar falha (o comando costuma ter chegado)
        time.sleep(1.5)
        uri_agora, contexto_agora, _ = _tocando_agora(token)
        if uri == uri_agora or (uri == contexto_agora and contexto_agora):
            return f"Tocando {nome}{de} no Spotify."
        raise SpotifyErro("a rede falhou no meio do play - tente de novo")
    msg = (dados or {}).get("error", {}).get("message", f"HTTP {status}")
    if status == 403:
        raise SpotifyErro("o Spotify recusou o play (controle remoto exige conta Premium)")
    raise SpotifyErro(f"play falhou: {msg}")


def controlar(acao):
    """pausar | continuar | proxima | anterior | que_musica."""
    token = _obter_token()
    rotas = {
        "pausar": ("PUT", "/me/player/pause", "Pausado, senhor."),
        "continuar": ("PUT", "/me/player/play", "Continuando a musica, senhor."),
        "proxima": ("POST", "/me/player/next", "Proxima faixa, senhor."),
        "anterior": ("POST", "/me/player/previous", "Voltando uma faixa, senhor."),
    }
    if acao == "que_musica":
        status, dados = _req("GET", "/me/player/currently-playing", token)
        if status == 200 and dados and dados.get("item"):
            nome = dados["item"]["name"]
            artistas = ", ".join(a["name"] for a in dados["item"].get("artists", []))
            return f"Esta tocando {nome}, de {artistas}."
        return "Nada tocando no momento, senhor."
    if acao not in rotas:
        return f"ERRO: acao desconhecida '{acao}'."
    metodo, caminho, ok_msg = rotas[acao]
    status, dados = _req(metodo, caminho, token)
    if status in (200, 202, 204):
        return ok_msg
    if status is None:
        # resposta perdida na rede: para pausar/continuar da para conferir
        # o estado real do player; pular/voltar quase sempre ja executou
        if acao in ("pausar", "continuar"):
            time.sleep(1.0)
            _, _, tocando = _tocando_agora(token)
            esperado = (acao == "continuar")
            if tocando is not None and tocando == esperado:
                return ok_msg
            raise SpotifyErro("a rede falhou no meio do comando - tente de novo")
        return ok_msg
    if status == 404:
        return "Nao ha player ativo no Spotify agora, senhor."
    if status == 403:
        raise SpotifyErro("controle do player exige conta Premium")
    msg = (dados or {}).get("error", {}).get("message", f"HTTP {status}")
    raise SpotifyErro(f"controle falhou: {msg}")
