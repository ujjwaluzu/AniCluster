import requests
from django.shortcuts import render, redirect
import os
from dotenv import load_dotenv

load_dotenv()

TMDB_KEY = os.getenv("TMDB_KEY")


ANILIST_API = "https://graphql.anilist.co"

def search_anime(query):

    graphql_query = """
    query ($search: String) {
      Page(page: 1, perPage: 20) {
        media(search: $search, type: ANIME) {
          id
          idMal
          title {
            romaji
            english
          }
          coverImage {
            large
          }
        }
      }
    }
    """

    variables = {"search": query}

    response = requests.post(
        ANILIST_API,
        json={"query": graphql_query, "variables": variables}
    )

    return response.json()["data"]["Page"]["media"]


def home(request):

    graphql_query = """
    query {
      trending: Page(page:1, perPage:5) {
        media(sort: TRENDING_DESC, type: ANIME) {
          idMal
          title { romaji english }
          coverImage { large }
          bannerImage
        }
      }

      popular: Page(page:1, perPage:20) {
        media(sort: POPULARITY_DESC, type: ANIME) {
          idMal
          title { romaji english }
          coverImage { large }
        }
      }

      airing: Page(page:1, perPage:12) {
        media(sort: TRENDING_DESC, status: RELEASING, type: ANIME) {
          idMal
          title { romaji english }
          coverImage { large }
        }
      }
    }
    """

    response = requests.post(
        ANILIST_API,
        json={"query": graphql_query}
    )

    data = response.json()["data"]

    featured = data["trending"]["media"]
    popular = data["popular"]["media"]
    airing = data["airing"]["media"]

    return render(request, "home.html", {
        "featured": featured,
        "popular": popular,
        "airing": airing
    })
def search(request):

    query = request.GET.get("q")

    anime_list = []

    if query:
        anime_list = search_anime(query)

    return render(request, "search.html", {
        "query": query,
        "results": anime_list
    })

def anime_detail(request, mal_id):
    graphql_query = """
    query ($malId: Int) {
      Media(idMal: $malId, type: ANIME) {
        idMal
        format
        episodes
        status
        season
        seasonYear
        title { romaji english }
        description
        coverImage { large }
        startDate { year month day }          # ← added
        relations {
          edges {
            relationType
            node {
              idMal
              title { romaji english }
              coverImage { large }
              startDate { year month day }    # ← added
            }
          }
        }
      }
    }
    """
    response = requests.post(
        ANILIST_API,
        json={"query": graphql_query, "variables": {"malId": mal_id}}
    )
    data = response.json()["data"]["Media"]
    if not data:
        return redirect("home")

    anime = data
    title = anime["title"]["english"] or anime["title"]["romaji"]
    external_ids = get_external_ids(title)   # we'll update this function later

    # --- Build franchise list for season numbering ---
    franchise = []
    # current anime
    franchise.append({
        'idMal': anime['idMal'],
        'title': anime['title'],
        'startDate': anime.get('startDate', {}),
    })
    # add sequels/prequels from relations
    for edge in anime['relations']['edges']:
        if edge['relationType'] in ['SEQUEL', 'PREQUEL']:
            node = edge['node']
            if node and node.get('idMal'):
                franchise.append({
                    'idMal': node['idMal'],
                    'title': node['title'],
                    'startDate': node.get('startDate', {}),
                })

    # sort by startDate (year, month, day) – missing dates go to the end
    def date_key(item):
        sd = item['startDate']
        if not sd or not sd.get('year'):
            return (9999, 99, 99)
        return (sd.get('year', 9999), sd.get('month', 99), sd.get('day', 99))

    franchise.sort(key=date_key)

    # assign season numbers (1‑based)
    season_map = {}          # idMal → season number
    for idx, item in enumerate(franchise, start=1):
        season_map[item['idMal']] = idx

    current_season = season_map.get(anime['idMal'], 1)

    # enhance the seasons list for the template
    enhanced_seasons = []
    for edge in anime['relations']['edges']:
        if edge['relationType'] in ['SEQUEL', 'PREQUEL']:
            node = edge['node']
            if node and node.get('idMal') and node['idMal'] != mal_id:
                node_copy = node.copy()
                node_copy['season_number'] = season_map.get(node['idMal'], 1)
                enhanced_seasons.append(node_copy)

    # related (excluding sequels/prequels)
    related = []
    for edge in anime['relations']['edges']:
        node = edge['node']
        if node and node.get('idMal') and node['idMal'] != mal_id:
            if edge['relationType'] not in ['SEQUEL', 'PREQUEL']:
                related.append(node)

    return render(request, "anime.html", {
        "anime": anime,
        "seasons": enhanced_seasons,            # now with season_number
        "related": related,
        "imdb": external_ids.get('imdb'),
        "tmdb": external_ids.get('tmdb'),       # also pass tmdb
        "current_season": current_season,
    })

def watch(request, mal_id, episode):
    imdb = request.GET.get("imdb")
    tmdb = request.GET.get("tmdb")
    server = request.GET.get("server", "vidsrc")
    season = request.GET.get("season", 1)

    # fetch anime details from Anilist
    graphql_query = """
    query ($malId: Int) {
      Media(idMal: $malId, type: ANIME) {
        title { romaji english }
        episodes
        format
      }
    }
    """
    response = requests.post(
        ANILIST_API,
        json={"query": graphql_query, "variables": {"malId": mal_id}}
    )
    anime = response.json()["data"]["Media"]
    total_episodes = anime["episodes"] or 1

    # if neither imdb nor tmdb is provided, try to fetch them now
    if not imdb and not tmdb:
        title = anime["title"]["english"] or anime["title"]["romaji"]
        external_ids = get_external_ids(title)
        imdb = external_ids.get('imdb')
        tmdb = external_ids.get('tmdb')

    embed_url = "about:blank"

    # ---------- MOVIES ----------
    if anime["format"] == "MOVIE":
        if server == "vidsrc":
            if imdb:
                embed_url = f"https://vidsrcme.ru/embed/movie?imdb={imdb}&autoplay=1"
            elif tmdb:
                embed_url = f"https://vidsrcme.ru/embed/movie?tmdb={tmdb}&autoplay=1"
        elif server == "superembed":
            if imdb:
                embed_url = f"https://multiembed.mov/?video_id={imdb}"
            elif tmdb:
                embed_url = f"https://multiembed.mov/?video_id={tmdb}&tmdb=1"

    # ---------- SERIES ----------
    else:
        if server == "vidsrc":
            if imdb:
                embed_url = f"https://vidsrcme.ru/embed/tv?imdb={imdb}&season={season}&episode={episode}&autoplay=1&autonext=1"
        elif server == "superembed":
            if imdb:
                embed_url = f"https://multiembed.mov/?video_id={imdb}&s={season}&e={episode}"
            elif tmdb:
                embed_url = f"https://multiembed.mov/?video_id={tmdb}&tmdb=1&s={season}&e={episode}"

    return render(request, "watch.html", {
        "embed_url": embed_url,
        "episode": episode,
        "season": season,
        "total_episodes": total_episodes,
        "mal_id": mal_id,
        "imdb": imdb,
        "tmdb": tmdb,
        "anime": anime,
        "server": server
    })


def landing(request):
    return render(request, "landing.html")

def get_external_ids(title):
    """Search TMDB for TV or movie and return dict with imdb_id and tmdb_id."""
    result = {'imdb': None, 'tmdb': None}

    # try TV first
    tv_search = requests.get(
        "https://api.themoviedb.org/3/search/tv",
        params={"api_key": TMDB_KEY, "query": title}
    ).json()
    if tv_search.get("results"):
        tmdb_id = tv_search["results"][0]["id"]
        details = requests.get(
            f"https://api.themoviedb.org/3/tv/{tmdb_id}",
            params={"api_key": TMDB_KEY, "append_to_response": "external_ids"}
        ).json()
        result['tmdb'] = tmdb_id
        result['imdb'] = details.get("external_ids", {}).get("imdb_id")
        if result['imdb']:
            return result

    # if not found, try movie
    movie_search = requests.get(
        "https://api.themoviedb.org/3/search/movie",
        params={"api_key": TMDB_KEY, "query": title}
    ).json()
    if movie_search.get("results"):
        tmdb_id = movie_search["results"][0]["id"]
        details = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            params={"api_key": TMDB_KEY, "append_to_response": "external_ids"}
        ).json()
        result['tmdb'] = tmdb_id
        result['imdb'] = details.get("external_ids", {}).get("imdb_id")
        return result

    return result