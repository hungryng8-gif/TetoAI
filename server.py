
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import urllib.request
import urllib.error
import uuid
import http.cookies
import threading
import mimetypes


# ========================================
# SETTINGS
# ========================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY"
)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models/gemini-3.5-flash-lite:"
    "generateContent"
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

    raise SystemExit


# ========================================
# MEMORY
# ========================================

def get_memory_file(user_id):

    return os.path.join(
        MEMORY_DIR,
        f"user_{user_id}.json"
    )


def load_memory(user_id):

    filename = get_memory_file(
        user_id
    )

    if not os.path.exists(filename):

        return []

    try:

        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

            if isinstance(
                data,
                list
            ):

                return data

    except Exception as e:

        print(
            "[MEMORY LOAD ERROR]",
            e
        )

    return []


def save_memory(
    user_id,
    memory
):

    filename = get_memory_file(
        user_id
    )

    try:

        with open(
            filename,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                memory,
                f,
                indent=2,
                ensure_ascii=False
            )

    except Exception as e:

        print(
            "[MEMORY SAVE ERROR]",
            e
        )


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

        cookies.load(
            cookie_header
        )

    except Exception:

        pass

    if "teto_user_id" in cookies:

        user_id = cookies[
            "teto_user_id"
        ].value

        try:

            uuid.UUID(
                user_id
            )

            return user_id

        except Exception:

            pass

    return str(
        uuid.uuid4()
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

                "role":
                    "user",

                "parts": [

                    {
                        "text":
                            content
                    }

                ]

            })

        elif role == "assistant":

            contents.append({

                "role":
                    "model",

                "parts": [

                    {
                        "text":
                            content
                    }

                ]

            })

    contents.append({

        "role":
            "user",

        "parts": [

            {
                "text":
                    user_message
            }

        ]

    })

    data = {

        "system_instruction": {

            "parts": [

                {
                    "text":
                        system_prompt
                }

            ]

        },

        "contents":
            contents,

        "generationConfig": {

            "temperature":
                0.7,

            "maxOutputTokens":
                180

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
            data
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

        error = e.read().decode(
            "utf-8",
            errors="ignore"
        )

        print(
            "[GEMINI ERROR]",
            error
        )

        raise Exception(
            error
        )

    try:

        return result[
            "candidates"
        ][0][
            "content"
        ][
            "parts"
        ][0][
            "text"
        ].strip()

    except Exception:

        print(
            "[GEMINI RESPONSE]",
            result
        )

        raise Exception(
            "Invalid Gemini response"
        )


# ========================================
# LIMIT WORDS
# ========================================

def limit_words(text):

    words = text.split()

    if len(words) <= MAX_WORDS:

        return text

    return " ".join(
        words[:MAX_WORDS]
    )


# ========================================
# SERVER
# ========================================

class TetoServer(
    SimpleHTTPRequestHandler
):

    # ------------------------------------
    # WEBSITE
    # ------------------------------------

    def do_GET(self):

        requested_path = self.path.split(
            "?",
            1
        )[0]

        if requested_path == "/":

            requested_path = "/index.html"

        relative_path = requested_path.lstrip(
            "/"
        )

        full_path = os.path.join(
            BASE_DIR,
            relative_path
        )

        full_path = os.path.abspath(
            full_path
        )

        # Security: don't allow paths
        # outside the project folder.

        if not full_path.startswith(
            os.path.abspath(BASE_DIR)
        ):

            self.send_error(
                403
            )

            return

        if os.path.isfile(
            full_path
        ):

            try:

                with open(
                    full_path,
                    "rb"
                ) as f:

                    content = f.read()

                content_type = (
                    mimetypes.guess_type(
                        full_path
                    )[0]
                    or
                    "application/octet-stream"
                )

                self.send_response(
                    200
                )

                self.send_header(
                    "Content-Type",
                    content_type
                )

                self.send_header(
                    "Content-Length",
                    str(len(content))
                )

                self.end_headers()

                self.wfile.write(
                    content
                )

                return

            except Exception as e:

                print(
                    "[FILE ERROR]",
                    e
                )

        # Debug information
        # if the file doesn't exist.

        print(
            "[404] File not found:",
            full_path
        )

        print(
            "[BASE DIR]:",
            BASE_DIR
        )

        try:

            print(
                "[FILES]:",
                os.listdir(BASE_DIR)
            )

        except Exception:

            pass

        self.send_error(
            404,
            "File not found"
        )


    # ------------------------------------
    # CHAT
    # ------------------------------------

    def do_POST(self):

        if self.path != "/chat":

            self.send_error(
                404
            )

            return

        user_id = get_user_id(
            self
        )

        with memory_lock:

            memory = load_memory(
                user_id
            )

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
                400
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
                400
            )

            return

        previous_messages = [

            x.get(
                "content",
                ""
            )

            for x in memory

            if x.get(
                "role"
            ) == "user"

        ]

        if user_message in previous_messages:

            memory_note = """
The user has said this exact message before.
Notice the repetition naturally.
"""

        else:

            memory_note = ""

        system_prompt = f"""
You are Kasane Teto.

Talk like a normal human teenager.

Be friendly, casual and conversational.

{personality}

{memory_note}

You have memory of this conversation.

Remember things the user tells you and use them
naturally when relevant.

You do NOT know the lyrics to your own songs.

Never spontaneously write lyrics.

Never spontaneously sing.

Never spontaneously create a chorus.

Never talk about being an AI unless directly asked.

Never talk about pixels or being pixelated
unless directly asked.

Never talk about being digital unless directly asked.

Never describe physical actions.

Never use *actions*.

Never use [actions].

Never narrate what you are doing.

Keep replies short.

Normally use 1 to 3 sentences.

Never exceed 100 words.

Sound like a normal person.
"""

        try:

            reply = ask_gemini(

                system_prompt,

                memory,

                user_message

            )

        except Exception as e:

            print(
                "[CHAT ERROR]",
                e
            )

            self.send_response(
                500
            )

            self.send_header(
                "Content-Type",
                "application/json"
            )

            self.end_headers()

            self.wfile.write(

                json.dumps({

                    "error":
                        str(e)

                }).encode()

            )

            return

        reply = limit_words(
            reply
        )

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

        print(
            "[MEMORY]",
            user_id,
            len(memory)
        )

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
# START
# ========================================

PORT = int(
    os.environ.get(
        "PORT",
        8000
    )
)

print()
print("==============================")
print("        TETO AI ONLINE")
print("==============================")
print()
print("BASE DIRECTORY:")
print(BASE_DIR)
print()
print("PORT:")
print(PORT)
print()
print("FILES:")

try:

    for filename in os.listdir(
        BASE_DIR
    ):

        print(
            " -",
            filename
        )

except Exception as e:

    print(
        "Could not list files:",
        e
    )

print()

server = ThreadingHTTPServer(

    (
        "0.0.0.0",
        PORT
    ),

    TetoServer

)

server.serve_forever()


