from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import urllib.request
import urllib.error
import uuid
import http.cookies
import threading


# ========================================
# SETTINGS
# ========================================

GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY"
)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models/gemini-3.5-flash-lite:"
    "generateContent"
)

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

MEMORY_DIR = os.path.join(
    BASE_DIR,
    "memories"
)

MAX_WORDS = 100
MAX_MEMORY_MESSAGES = 200

os.makedirs(
    MEMORY_DIR,
    exist_ok=True
)

memory_lock = threading.Lock()


# ========================================
# CHECK API KEY
# ========================================

if not GEMINI_API_KEY:

    print()
    print("==============================")
    print("ERROR: GEMINI_API_KEY missing")
    print("==============================")
    print()
    print("Run:")
    print()
    print('setx GEMINI_API_KEY "YOUR_KEY"')
    print()
    print("Then close and reopen Command Prompt.")
    print()

    raise SystemExit


# ========================================
# USER ID
# ========================================

def get_user_id(handler):

    cookie_header = handler.headers.get(
        "Cookie",
        ""
    )

    cookies = http.cookies.SimpleCookie()

    try:
        cookies.load(cookie_header)
    except Exception:
        pass

    if "teto_user_id" in cookies:

        user_id = cookies[
            "teto_user_id"
        ].value

        try:
            uuid.UUID(user_id)
            return user_id, False

        except ValueError:
            pass

    user_id = str(
        uuid.uuid4()
    )

    return user_id, True


# ========================================
# MEMORY FILE
# ========================================

def get_memory_file(user_id):

    return os.path.join(
        MEMORY_DIR,
        f"user_{user_id}.json"
    )


# ========================================
# LOAD MEMORY
# ========================================

def load_memory(user_id):

    memory_file = get_memory_file(
        user_id
    )

    if not os.path.exists(
        memory_file
    ):

        return []

    try:

        with open(
            memory_file,
            "r",
            encoding="utf-8"
        ) as f:

            memory = json.load(f)

        if isinstance(
            memory,
            list
        ):

            return memory

    except Exception as e:

        print(
            "[MEMORY] Load error:",
            e
        )

    return []


# ========================================
# SAVE MEMORY
# ========================================

def save_memory(
    user_id,
    memory
):

    memory_file = get_memory_file(
        user_id
    )

    with open(
        memory_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            memory,
            f,
            indent=2,
            ensure_ascii=False
        )


# ========================================
# WORD LIMIT
# ========================================

def limit_words(text):

    words = text.split()

    if len(words) <= MAX_WORDS:
        return text

    return " ".join(
        words[:MAX_WORDS]
    )


# ========================================
# GEMINI
# ========================================

def ask_gemini(
    system_prompt,
    memory,
    user_message
):

    contents = []

    # Previous conversation
    for item in memory[-30:]:

        role = item.get(
            "role"
        )

        content = item.get(
            "content",
            ""
        )

        if role == "user":

            contents.append({

                "role": "user",

                "parts": [
                    {
                        "text": content
                    }
                ]

            })

        elif role == "assistant":

            contents.append({

                "role": "model",

                "parts": [
                    {
                        "text": content
                    }
                ]

            })

    # Current message
    contents.append({

        "role": "user",

        "parts": [
            {
                "text": user_message
            }
        ]

    })

    # Gemini request
    gemini_data = {

        "system_instruction": {

            "parts": [
                {
                    "text": system_prompt
                }
            ]

        },

        "contents": contents,

        "generationConfig": {

            "temperature": 0.7,

            "maxOutputTokens": 180

        }

    }

    url = (
        GEMINI_URL
        + "?key="
        + GEMINI_API_KEY
    )

    request = urllib.request.Request(

        url,

        data=json.dumps(
            gemini_data
        ).encode("utf-8"),

        headers={
            "Content-Type":
                "application/json"
        },

        method="POST"

    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=60
        ) as response:

            result = json.loads(
                response.read()
                .decode("utf-8")
            )

    except urllib.error.HTTPError as e:

        error_body = e.read().decode(
            "utf-8",
            errors="ignore"
        )

        print(
            "[GEMINI ERROR]",
            error_body
        )

        raise Exception(
            f"Gemini HTTP {e.code}: "
            f"{error_body}"
        )

    except Exception as e:

        print(
            "[GEMINI ERROR]",
            e
        )

        raise

    # Get reply
    try:

        reply = result[
            "candidates"
        ][0][
            "content"
        ][
            "parts"
        ][0][
            "text"
        ]

    except Exception:

        print(
            "[GEMINI RESPONSE]",
            result
        )

        raise Exception(
            "Gemini returned an unexpected response."
        )

    return reply.strip()


# ========================================
# SERVER
# ========================================

class TetoServer(
    SimpleHTTPRequestHandler
):

    def do_POST(self):

        if self.path != "/chat":

            self.send_error(
                404
            )

            return

        # Get visitor ID
        user_id, is_new = get_user_id(
            self
        )

        # Load this visitor's memory
        with memory_lock:

            memory = load_memory(
                user_id
            )

        # Read request
        try:

            length = int(
                self.headers.get(
                    "Content-Length",
                    0
                )
            )

            body = self.rfile.read(
                length
            )

            data = json.loads(
                body
            )

        except Exception:

            self.send_error(
                400,
                "Invalid request"
            )

            return

        user_message = data.get(
            "message",
            ""
        ).strip()

        personality = data.get(
            "personality",
            ""
        )

        if not user_message:

            self.send_error(
                400,
                "Empty message"
            )

            return

        # Check repetition
        previous_messages = [

            x.get("content", "")

            for x in memory

            if x.get("role")
            == "user"

        ]

        if user_message in previous_messages:

            memory_note = """
The user has said this exact message before.
Notice the repetition naturally.
Do not pretend it is the first time.
"""

        else:

            memory_note = ""

        # =================================
        # TETO PERSONALITY
        # =================================

        system_prompt = f"""
You are Kasane Teto.

Talk like a normal human teenager.

Be friendly, casual and conversational.

{personality}

{memory_note}

You have memory of this conversation.

Remember information the user tells you
and use it naturally later when relevant.

If the user repeats something,
you can notice that you have heard it before.

You do NOT know the lyrics to your own songs.

You do NOT automatically know song lyrics
just because they are associated with Kasane Teto.

Never spontaneously write lyrics.

Never spontaneously sing.

Never spontaneously create a chorus.

Never talk about being an AI unless directly asked.

Never talk about pixels or being pixelated
unless directly asked.

Never talk about being digital
unless directly asked.

Never describe physical actions.

Never use *actions*.

Never use [actions].

Never narrate what you are doing.

Keep responses short.

Normally use 1 to 3 sentences.

Never exceed 100 words.

Do not make every response a paragraph.

Sound like an ordinary person having
a normal conversation.
"""

        # =================================
        # ASK GEMINI
        # =================================

        try:

            reply = ask_gemini(

                system_prompt,

                memory,

                user_message

            )

        except Exception as e:

            self.send_response(
                500
            )

            self.send_header(
                "Content-Type",
                "application/json"
            )

            self.send_header(
                "Access-Control-Allow-Origin",
                "*"
            )

            self.end_headers()

            self.wfile.write(

                json.dumps({

                    "error":
                        str(e)

                }).encode()

            )

            return

        # =================================
        # WORD LIMIT
        # =================================

        reply = limit_words(
            reply
        )

        # =================================
        # SAVE MEMORY
        # =================================

        memory.append({

            "role":
                "user",

            "content":
                user_message

        })

        memory.append({

            "role":
                "assistant",

            "content":
                reply

        })

        if len(memory) > MAX_MEMORY_MESSAGES:

            memory = memory[
                -MAX_MEMORY_MESSAGES:
            ]

        with memory_lock:

            save_memory(
                user_id,
                memory
            )

        print()
        print(
            "[MEMORY] User:",
            user_id
        )

        print(
            "[MEMORY] Messages:",
            len(memory)
        )

        # =================================
        # SEND RESPONSE
        # =================================

        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            "application/json"
        )

        self.send_header(
            "Cache-Control",
            "no-store"
        )

        self.send_header(
            "Set-Cookie",
            f"teto_user_id={user_id}; "
            f"Path=/; "
            f"HttpOnly; "
            f"SameSite=Lax"
        )

        self.end_headers()

        self.wfile.write(

            json.dumps({

                "reply":
                    reply

            }).encode()

        )


# ========================================
# START SERVER
# ========================================

server = ThreadingHTTPServer(

    (
        "0.0.0.0",
        8000
    ),

    TetoServer

)

print()
print("==============================")
print("        TETO AI ONLINE")
print("==============================")
print()
print("AI:")
print("Gemini 3.5 Flash-Lite")
print()
print("MEMORY:")
print("Separate memory for every visitor")
print()
print("MEMORY FOLDER:")
print(MEMORY_DIR)
print()
print("Open:")
print("http://127.0.0.1:8000")
print()

server.serve_forever()