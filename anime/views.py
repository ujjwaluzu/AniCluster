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

        title {
        romaji
        english
        }

        description

        coverImage {
        large
        }

        relations {
        edges {
            relationType
            node {
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
    }
    }
    """

    response = requests.post(
        ANILIST_API,
        json={
            "query": graphql_query,
            "variables": {"malId": mal_id}
        }
    )

    data = response.json()["data"]["Media"]

    if not data:
        return redirect("home")

    anime = data

    # get title
    title = anime["title"]["english"] or anime["title"]["romaji"]

    imdb_id = get_imdb_id(title)
    related = []

    for edge in anime["relations"]["edges"]:
        node = edge["node"]
        if node and node.get("idMal") and node["idMal"] != mal_id:
            related.append(node)
    # 🔹 extract seasons
    seasons = []

    for edge in anime["relations"]["edges"]:

        if edge["relationType"] in ["SEQUEL", "PREQUEL"]:

            seasons.append(edge["node"])

    return render(request, "anime.html", {
        "anime": anime,
        "seasons": seasons,
        "related": related[1:],
        "imdb": imdb_id
    })

def watch(request, mal_id, episode):

    imdb = request.GET.get("imdb")
    tmdb = request.GET.get("tmdb")

    graphql_query = """
    query ($malId: Int) {
      Media(idMal: $malId, type: ANIME) {
        title {
          romaji
          english
        }
        episodes
        format
      }
    }
    """

    response = requests.post(
        ANILIST_API,
        json={
            "query": graphql_query,
            "variables": {"malId": mal_id}
        }
    )

    anime = response.json()["data"]["Media"]
    total_episodes = anime["episodes"] or 1

    # MOVIE
    if anime["format"] == "MOVIE":

        if imdb:
            embed_url = f"https://vidsrcme.ru/embed/movie?imdb={imdb}&autoplay=1"

        elif tmdb:
            embed_url = f"https://vidsrcme.ru/embed/movie?tmdb={tmdb}&autoplay=1"

        else:
            embed_url = "about:blank"

    # TV / ANIME SERIES
    else:

        if imdb:
            embed_url = f"https://vidsrc-embed.ru/embed/tv?imdb={imdb}&season=1&episode={episode}&autoplay=1&autonext=1"

        else:
            embed_url = "about:blank"

    return render(request, "watch.html", {
        "embed_url": embed_url,
        "episode": episode,
        "total_episodes": total_episodes,
        "mal_id": mal_id,
        "imdb": imdb,
        "anime": anime
    })


def landing(request):
    return render(request, "landing.html")

def get_imdb_id(title):

    # search TV first
    tv_search = requests.get(
        "https://api.themoviedb.org/3/search/tv",
        params={
            "api_key": TMDB_KEY,
            "query": title
        }
    ).json()

    if tv_search["results"]:

        tmdb_id = tv_search["results"][0]["id"]

        details = requests.get(
            f"https://api.themoviedb.org/3/tv/{tmdb_id}",
            params={
                "api_key": TMDB_KEY,
                "append_to_response": "external_ids"
            }
        ).json()

        imdb = details["external_ids"].get("imdb_id")

        if imdb:
            return imdb


    # if not TV → search movie
    movie_search = requests.get(
        "https://api.themoviedb.org/3/search/movie",
        params={
            "api_key": TMDB_KEY,
            "query": title
        }
    ).json()

    if movie_search["results"]:

        tmdb_id = movie_search["results"][0]["id"]

        details = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            params={
                "api_key": TMDB_KEY,
                "append_to_response": "external_ids"
            }
        ).json()

        imdb = details["external_ids"].get("imdb_id")

        if imdb:
            return imdb

    return None