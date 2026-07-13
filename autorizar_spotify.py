"""Autorizacao unica do Spotify para o Jarvis (rode via Autorizar Spotify.bat).

Pre-requisitos:
  1. Criar um app em https://developer.spotify.com/dashboard
     - Redirect URI: http://127.0.0.1:8917/callback
     - Marcar "Web API"
  2. Colar o Client ID em config.json -> "spotify" -> "client_id"
"""
import sys

import spotify_api

try:
    if not spotify_api.configurado():
        print('Preencha antes o "client_id" na secao "spotify" do config.json')
        print("(crie o app em https://developer.spotify.com/dashboard com o")
        print(f" Redirect URI {spotify_api.REDIRECT_URI})")
        sys.exit(1)
    spotify_api.autorizar()
    print("\nTeste rapido: pedindo a musica atual...")
    print(" ", spotify_api.controlar("que_musica"))
    print("\nTudo pronto! O Jarvis ja pode dar play direto.")
except spotify_api.SpotifyErro as e:
    print(f"\nERRO: {e}")
    sys.exit(1)
