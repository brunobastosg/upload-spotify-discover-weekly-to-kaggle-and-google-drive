import os
import spotipy
import json
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path

COL_TRACK_NAME = 'Track Name'
COL_TRACK_URI = 'Track URI'
COL_ARTIST_NAMES = 'Artist Name(s)'
COL_ARTIST_URIS = 'Artist URI(s)'
COL_ALBUM_NAME = 'Album Name'
COL_ADDED_AT = 'Added At'

local_run = os.getenv('LOCAL_RUN', 'false')

if local_run.lower() == 'true':
    load_dotenv()

client_id = os.getenv('SPOTIFY_CLIENT_ID')
client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
redirect_uri = 'http://127.0.0.1:3000'

local_cache_exists = Path('.cache').is_file()

if not local_cache_exists and 'SPOTIFY_AUTH_CACHE' in os.environ:
    auth_cache = os.environ['SPOTIFY_AUTH_CACHE']

    with open('.cache', 'w', encoding='utf-8') as cache_file:
        cache_file.write(json.dumps(json.loads(auth_cache)))

sp = spotipy.Spotify(
    auth_manager=spotipy.SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope='playlist-read-private'
    )
)

playlists = sp.current_user_playlists()

discover_weekly = None
for playlist in playlists['items']:
    if playlist['name'] == 'Discover Weekly':
        discover_weekly = playlist
        break

if discover_weekly:
    print(f'Found "Discover Weekly" playlist. ID: {discover_weekly["id"]}')

    playlist_data = {
        COL_TRACK_NAME: [],
        COL_TRACK_URI: [],
        COL_ARTIST_NAMES: [],
        COL_ARTIST_URIS: [],
        COL_ALBUM_NAME: [],
        COL_ADDED_AT: []
    }

    musicas = sp.user_playlist_tracks(playlist_id=discover_weekly['id'])

    for item in musicas['items']:
        playlist_data[COL_TRACK_NAME].append(item['track']['name'])
        playlist_data[COL_TRACK_URI].append(item['track']['uri'])
        playlist_data[COL_ARTIST_NAMES].append(','.join([artist['name'] for artist in item['track']['artists']]))
        playlist_data[COL_ARTIST_URIS].append(','.join([artist['uri'] for artist in item['track']['artists']]))
        playlist_data[COL_ALBUM_NAME].append(item['track']['album']['name'])
        playlist_data[COL_ADDED_AT].append(item['added_at'])

    output_folder = Path('output')
    if not output_folder.is_dir():
        output_folder.mkdir()

    print('Saving playlist as CSV...')
    pd.DataFrame.from_dict(playlist_data).to_csv('output/this-weeks-playlist.csv', index=False)
    print('Playlist saved!')
else:
    raise('Discover Weekly playlist not found!')
