import streamlit as st
import requests
import time
import re
import os
import random
import isodate
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi
from langdetect import detect, LangDetectException

st.set_page_config(
    page_title="YouTube Shorts Skaner PL",
    page_icon="app_icon.ico",
    layout="wide"
)

# Ścieżka do logo.png
LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo.png")

# Klucze API
YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

POLISH_DISTINCT_WORDS = {
    "nie", "tak", "jest", "sie", "się", "jak", "ale", "dla", "od", 
    "juz", "już", "tylko", "bardzo", "fajne", "super", "ogladam", 
    "oglądam", "pozdrawiam", "odcinek", "czemu", "dlaczego", "kiedy",
    "zrobił", "zrobic", "zrobić", "filmik", "dobrze", "masakra", "haha",
    "hahaha", "śmieszne", "smieszne", "beka", "zgon", "popłakałem", "ubaw"
}

CATEGORY_TOPICS = {
    "Komediowe": [
        "#shorts śmieszne polska",
        "#shorts najlepsze wpadki polska",
        "#shorts kawały suchary",
        "#shorts śmieszne scenki",
        "#shorts standup polska żarty",
        "#shorts zabawne sytuacje polska",
        "#shorts humor z życia",
        "#shorts prank polska śmieszne",
        "#shorts dowcipy z brodą",
        "#shorts komedia polska",
        "#shorts beka z życia"
    ],
    "Ciekawostki": [
        "#shorts ciekawostki polska",
        "#shorts czy wiesz że polska",
        "#shorts fakty ze świata",
        "#shorts niesamowite historie polska",
        "#shorts wiedza w minutę",
        "#shorts tajemnice nauka ciekawostki",
        "#shorts rekordy świata polska",
        "#shorts historia ciekawostki"
    ],
    "Podcast": [
        "#shorts polski podcast wycinki",
        "#shorts najlepsze momenty podcast",
        "#shorts rozmowa wywiad polska",
        "#shorts podcast mądre słowa",
        "#shorts podcast dyskusja",
        "#shorts podcast gość polska",
        "#shorts fragmenty podcastu"
    ],
    "Gaming": [
        "#shorts polski gaming",
        "#shorts śmieszne momenty gry",
        "#shorts polski streamer wpadka",
        "#shorts gry ciekawostki polska",
        "#shorts najlepsze akcje gry",
        "#shorts gaming polska twitch",
        "#shorts gameplay polska"
    ],
    "Jedzenie": [
        "#shorts przepis w minutę",
        "#shorts szybkie gotowanie polska",
        "#shorts test jedzenia polska",
        "#shorts pyszne jedzenie przepis",
        "#shorts kulinaria street food polska",
        "#shorts recenzja restauracji polska",
        "#shorts ciasto prosty przepis"
    ]
}

STYLE_INSTRUCTIONS = {
    "Standardowy": "Pisz w sposób neutralny, poprawną polszczyzną, konkretnie i zwięźle przedstawiając sytuację bez slangów.",
    "Młodzieżowy": "Używaj współczesnego polskiego slangu młodzieżowego i internetowego (np. beka, rel, odklejka, cringe, baza, sigma, dymy, hit). Zero nudy i formalizmów.",
    "Komentator sportowy / Na żywo": "Pisz jak podekscytowany komentator sportowy prowadzący relację na żywo z wielkiego meczu lub gali – dużo emocji, wykrzykniki, dynamiczne zwroty akcji i tempo!",
    "Sarkastyczny / Złośliwy": "Pisz z dużą dawką ironii, ciętego humoru i lekkiego szyderstwa z bohaterów nagrania lub sytuacji.",
    "Dramatyczny / Filmowy": "Pisz jak lektor zwiastuna hollywoodzkiego hitu – buduj przesadny patos, wielkie napięcie, szok i dramat z błahych wydarzeń."
}


def render_iframe(src, width=315, height=560):
    """Zgodność z nowym st.iframe oraz starszym st.components.v1.iframe bez nieobsługiwanych argumentów."""
    if hasattr(st, "iframe"):
        st.iframe(src, width=width, height=height)
    else:
        st.components.v1.iframe(src, width=width, height=height, scrolling=False)


def render_stretched_image(image_path):
    """Dopasowuje logo do pełnej szerokości paska bocznego."""
    try:
        st.image(image_path, width="stretch")
    except TypeError:
        st.image(image_path, use_container_width=True)


def get_youtube_service():
    return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)


def is_strictly_polish(text):
    text_clean = text.strip()
    words = re.findall(r'\b[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+\b', text_clean.lower())
    
    polish_chars = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
    if any(ch in polish_chars for ch in text_clean):
        return True

    try:
        detected_lang = detect(text_clean)
        if detected_lang == "pl":
            return True
        if detected_lang in ["en", "es", "de", "it", "fr", "pt", "ru", "uk"]:
            return False
    except LangDetectException:
        pass

    matched_words = [w for w in words if w in POLISH_DISTINCT_WORDS]
    if len(matched_words) >= 1 and len(words) <= 8:
        return True

    return False


def is_polish_title(title):
    if any(ch in set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ") for ch in title):
        return True
    try:
        lang = detect(title)
        return lang != "en"
    except LangDetectException:
        return True


def search_shorts_candidates(youtube, query, page_token=None):
    try:
        sort_order = random.choice(["relevance", "viewCount", "rating"])
        request = youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            videoDuration="short",
            order=sort_order,
            regionCode="PL",
            relevanceLanguage="pl",
            maxResults=35,
            pageToken=page_token
        )
        return request.execute()
    except Exception as e:
        st.error(f"Błąd YouTube Search API: {e}")
        return {}


def get_videos_details(youtube, video_ids):
    try:
        request = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids)
        )
        return request.execute().get("items", [])
    except Exception:
        return []


def get_top_polish_comments(youtube, video_id, target_comments=5, max_words=50):
    try:
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            order="relevance",
            maxResults=50,
            textFormat="plainText"
        )
        response = request.execute()

        polish_comments = []
        for item in response.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            content = top["textDisplay"].strip()
            word_count = len(content.split())

            if 0 < word_count <= max_words and is_strictly_polish(content):
                polish_comments.append({
                    "author": top["authorDisplayName"],
                    "text": content,
                    "likes": int(top["likeCount"])
                })

        polish_comments.sort(key=lambda x: x["likes"], reverse=True)
        return polish_comments[:target_comments]
    except HttpError:
        return []


def get_video_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["pl"])
        return " ".join([entry["text"] for entry in transcript])[:1500]
    except Exception:
        return "Brak polskich napisów."


def analyze_with_ai(video_title, transcript, description, comments, selected_style):
    comments_formatted = "\n".join(
        [f"- [{c['likes']} polubień] {c['author']}: \"{c['text']}\"" for c in comments]
    )

    style_guide = STYLE_INSTRUCTIONS.get(selected_style, STYLE_INSTRUCTIONS["Standardowy"])

    prompt = f"""
Przeanalizuj poniższy materiał z YouTube Shorts. 
Twoim jedynym zadaniem jest krótki opis tego, co dzieje się na nagraniu.

Styl narracji: {selected_style}
Wskazówki stylu: {style_guide}

Zasady:
1. Maksymalnie 50 wyrazów.
2. Trzymaj się ściśle narzuconego stylu narracji ({selected_style}).
3. Nie dodawaj wstępów typu "W filmie widzimy...", powitań ani podsumowań. Od razu przejdź do sedna akcji.

Tytuł wideo: {video_title}
Opis: {description}
Treść/Transkrypcja: {transcript}
Komentarze widzów:
{comments_formatted}
"""

    models_to_try = [
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
    ]

    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    last_error = ""
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=25)
            res_json = res.json()
            if "error" in res_json:
                error_msg = res_json["error"].get("message", "")
                last_error = error_msg
                if any(x in error_msg for x in ["Quota", "demand", "503", "no longer available"]):
                    time.sleep(1)
                    continue
                raise Exception(error_msg)
            return res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            last_error = str(e)
            continue

    return f"Błąd generowania opisu: {last_error}"


# --- INTERFEJS STREAMLIT ---

st.title("📱 YouTube Shorts Skaner PL")
st.caption("Losowe shorty z polskiej bazy YouTube")

# Panel boczny
with st.sidebar:
    if os.path.exists(LOGO_PATH):
        render_stretched_image(LOGO_PATH)
    
    st.header("⚙ Ustawienia skanera")
    
    selected_category = st.selectbox(
        "Rodzaj shortów:",
        options=["Komediowe", "Ciekawostki", "Podcast", "Gaming", "Jedzenie"],
        index=0
    )
    
    min_comm = st.slider("Minimalna liczba komentarzy pod filmem:", min_value=0, max_value=100, value=10, step=5)
    target_results = st.slider("Liczba shortów do wyświetlenia:", min_value=1, max_value=20, value=5, step=1)
    
    selected_style = st.selectbox(
        "Styl opisu akcji (slang):",
        options=[
            "Standardowy",
            "Młodzieżowy",
            "Komentator sportowy / Na żywo",
            "Sarkastyczny / Złośliwy",
            "Dramatyczny / Filmowy"
        ],
        index=0
    )
    
    run_btn = st.button("🎲 Losuj Shorty", type="primary")

if run_btn:
    youtube = get_youtube_service()
    valid_shorts = []
    seen_channels = set()

    available_topics = CATEGORY_TOPICS.get(selected_category, CATEGORY_TOPICS["Komediowe"])
    topics_pool = random.sample(available_topics, len(available_topics))
    topic_idx = 0

    progress_bar = st.progress(0)
    status_text = st.empty()

    required_comments_count = min(min_comm, 5)

    while len(valid_shorts) < target_results and topic_idx < len(topics_pool):
        current_query = topics_pool[topic_idx]
        topic_idx += 1

        search_res = search_shorts_candidates(youtube, query=current_query)
        items = search_res.get("items", [])
        if not items:
            continue

        video_ids = [it["id"]["videoId"] for it in items if "videoId" in it.get("id", {})]
        if not video_ids:
            continue

        details = get_videos_details(youtube, video_ids)
        random.shuffle(details)

        for video in details:
            duration_str = video.get("contentDetails", {}).get("duration", "PT0S")
            duration_sec = isodate.parse_duration(duration_str).total_seconds()
            if duration_sec <= 0 or duration_sec > 60:
                continue

            stats = video.get("statistics", {})
            comment_count = int(stats.get("commentCount", 0))
            if comment_count < min_comm:
                continue

            channel_title = video["snippet"].get("channelTitle", "").strip()

            if channel_title.lower() in seen_channels:
                continue

            title = video["snippet"]["title"]

            if not is_polish_title(title):
                continue

            status_text.text(f"Sprawdzam: {title[:35]}... ({len(valid_shorts)}/{target_results})")

            comments = get_top_polish_comments(youtube, video["id"], target_comments=5, max_words=50)
            if len(comments) >= required_comments_count:
                seen_channels.add(channel_title.lower())
                valid_shorts.append({
                    "video_id": video["id"],
                    "title": title,
                    "channel": channel_title,
                    "description": video["snippet"]["description"],
                    "comment_count": comment_count,
                    "views": stats.get("viewCount", "0"),
                    "duration": int(duration_sec),
                    "url": f"https://www.youtube.com/shorts/{video['id']}",
                    "embed_url": f"https://www.youtube.com/embed/{video['id']}",
                    "top_comments": comments,
                    "transcript": get_video_transcript(video["id"])
                })

                progress_bar.progress(len(valid_shorts) / target_results)

                if len(valid_shorts) == target_results:
                    break

    status_text.empty()
    progress_bar.empty()

    if not valid_shorts:
        st.warning("Nie znaleziono materiałów spełniających kryteria. Spróbuj kliknąć ponownie lub obniżyć próg komentarzy.")
    else:
        st.success(f"Wylosowano {len(valid_shorts)} shortów z kategorii: {selected_category}!")

        ai_placeholders = []

        # ETAP 1: Szybkie renderowanie filmów i komentarzy
        for i, video in enumerate(valid_shorts, start=1):
            st.markdown("---")
            col_phone, col_details = st.columns([1, 1.6])

            with col_phone:
                st.markdown(f"**Czas trwania:** {video['duration']} sek.")
                render_iframe(video["embed_url"], width=315, height=560)
                st.write(f"**Kanał:** {video['channel']}")
                st.write(f"💬 Komentarze: {video['comment_count']} | 👁️ Wyświetlenia: {video['views']}")
                st.markdown(f"[🔗 Otwórz w aplikacji YouTube Shorts]({video['url']})")

            with col_details:
                st.subheader(f"{i}. {video['title']}")
                st.markdown(f"##### 📝 Krótko. Co się dzieje na filmie ? *(styl: {selected_style})*")
                
                desc_placeholder = st.empty()
                desc_placeholder.info("⏳ Oczekiwanie na wygenerowanie opisu...")
                ai_placeholders.append(desc_placeholder)

                with st.expander("💬 5 najpopularniejszych polskich komentarzy", expanded=True):
                    if video["top_comments"]:
                        for c in video["top_comments"]:
                            st.markdown(f"👍 **{c['likes']}** | **{c['author']}**: {c['text']}")
                    else:
                        st.write("Brak komentarzy spełniających kryteria.")

        # ETAP 2: Generowanie opisów AI w tle
        with st.status(f"🤖 Generowanie opisów w stylu: {selected_style}...", expanded=False) as ai_status:
            for idx, video in enumerate(valid_shorts):
                ai_placeholders[idx].warning("⚡ Generuję opis...")
                summary = analyze_with_ai(
                    video["title"],
                    video["transcript"],
                    video["description"],
                    video["top_comments"],
                    selected_style=selected_style
                )
                ai_placeholders[idx].info(summary)
            ai_status.update(label=f"✅ Wszystkie opisy wygenerowane w stylu: {selected_style}!", state="complete")