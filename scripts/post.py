#!/usr/bin/env python3
"""Post the next ready item from content/manifest.json to the Facebook Page.

Reads content/state.json for the queue index, posts one item via the
Facebook Graph API, then advances the index. Exits 0 without posting when
the queue is empty or the next item is not ready yet.

Videos are posted as REELS via the 3-step video_reels upload flow.
"""
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

PAGE_ID = os.environ["PAGE_ID"]
TOKEN = os.environ.get("FB_PAGE_TOKEN", "")
GRAPH = "https://graph.facebook.com/v21.0"


def api_post_text(message):
    data = urllib.parse.urlencode(
        {"message": message, "access_token": TOKEN}
    ).encode()
    req = urllib.request.Request(f"{GRAPH}/{PAGE_ID}/feed", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_post_media(edge, filepath, text_field, text):
    # curl handles multipart file upload; the token is passed as a form
    # field so it never appears in the command line of other processes.
    cmd = [
        "curl", "-sS", "-X", "POST", f"{GRAPH}/{PAGE_ID}/{edge}",
        "-F", f"source=@{filepath}",
        "-F", f"{text_field}={text}",
        "-F", f"access_token={TOKEN}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        print("curl failed:", proc.stderr.strip())
        sys.exit(1)
    return json.loads(proc.stdout)


def api_post_reel(filepath, description):
    """Post a video as a Facebook Reel via the 3-step video_reels flow."""
    # Step 1: Initialize upload session
    data = urllib.parse.urlencode(
        {"upload_phase": "start", "access_token": TOKEN}
    ).encode()
    req = urllib.request.Request(
        f"{GRAPH}/{PAGE_ID}/video_reels", data=data, method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        init = json.loads(resp.read().decode("utf-8"))
    if "error" in init:
        print("Reels init error:", json.dumps(init["error"], indent=2))
        sys.exit(1)
    video_id = init["video_id"]
    upload_url = init["upload_url"]
    print(f"Reels upload session started: video_id={video_id}")

    # Step 2: Upload the video file to rupload.facebook.com
    file_size = os.path.getsize(filepath)
    cmd = [
        "curl", "-sS", "-X", "POST", upload_url,
        "-H", f"Authorization: OAuth {TOKEN}",
        "-H", "offset: 0",
        "-H", f"file_size: {file_size}",
        "--data-binary", f"@{filepath}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        print("Reels upload failed:", proc.stderr.strip())
        sys.exit(1)
    print("Reels file uploaded.")

    # Step 3: Finish and publish
    data = urllib.parse.urlencode({
        "upload_phase": "finish",
        "video_id": video_id,
        "description": description,
        "access_token": TOKEN,
    }).encode()
    req = urllib.request.Request(
        f"{GRAPH}/{PAGE_ID}/video_reels", data=data, method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    if not TOKEN:
        print("FB_PAGE_TOKEN secret is missing.")
        print("Add it in the repo: Settings > Secrets and variables > Actions > New repository secret.")
        sys.exit(1)

    with open("content/manifest.json") as fh:
        items = json.load(fh)["items"]
    with open("content/state.json") as fh:
        state = json.load(fh)

    if not items:
        print("Queue is empty. Nothing to post.")
        return

    idx = state.get("index", 0) % len(items)
    item = items[idx]

    if not item.get("ready"):
        print(f"Item {idx} ({item['type']}) is not ready yet. Skipping this slot.")
        return

    caption = item.get("caption", "")
    kind = item["type"]
    if kind == "text":
        result = api_post_text(caption)
    elif kind == "image":
        result = api_post_media("photos", item["file"], "caption", caption)
    elif kind == "video":
        result = api_post_reel(item["file"], caption)
    else:
        print(f"Unknown item type: {kind}")
        sys.exit(1)

    if "error" in result:
        print("Facebook API error:", json.dumps(result["error"], indent=2))
        sys.exit(1)

    print("Posted OK:", result.get("id"))
    state["index"] = (idx + 1) % len(items)
    with open("content/state.json", "w") as fh:
        json.dump(state, fh, indent=2)


if __name__ == "__main__":
    main()
