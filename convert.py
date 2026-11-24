#!/usr/bin/env python3
"""
MineVideo for Minecraft Bedrock
Video file or link  ->  .mcaddon (behavior pack + resource pack)

The addon plays the video on a floating screen entity (frames + audio).
Bedrock cannot decode or stream video by itself, so this tool pre-converts it.

Usage examples
  python convert.py --input clip.mp4 --name MyClip
  python convert.py --url https://example.com/clip.mp4 --seconds 30 --fps 10 --width 192
Needs: Python 3.8+, ffmpeg (with libvorbis) and ffprobe in PATH.
Optional: yt-dlp for page links (only use videos you have the right to use).
"""
import argparse
import glob
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import uuid
import zipfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
VIDEO_EXT = (".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".gif")


def sh(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        print(r.stdout)
        sys.exit("Command failed: " + " ".join(cmd[:3]) + " ...")
    return r.stdout


def png_size(path):
    with open(path, "rb") as f:
        d = f.read(24)
    return struct.unpack(">II", d[16:24])


def is_direct(url):
    return bool(re.search(r"\.(mp4|m4v|mov|webm|mkv|avi|gif)(\?|#|$)", url, re.I))


def download(url, work):
    if is_direct(url):
        dest = os.path.join(work, "input_video" + os.path.splitext(url.split("?")[0])[1])
        print("Downloading direct link ...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=90) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
        return dest
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        sys.exit("This link is not a direct video file and yt-dlp is not installed.\n"
                 "Use a direct .mp4 link, or install yt-dlp (pip install yt-dlp).")
    print("Using yt-dlp. Only convert videos you have the right to use.")
    sh([ytdlp, "-f", "best[height<=480]/best", "-o", os.path.join(work, "input_video.%(ext)s"), url])
    found = glob.glob(os.path.join(work, "input_video.*"))
    if not found:
        sys.exit("yt-dlp did not produce a file.")
    return found[0]


def pick_input(args, work):
    if args.url:
        return download(args.url, work)
    if args.input:
        if not os.path.isfile(args.input):
            sys.exit("Input file not found: " + args.input)
        return args.input
    for f in sorted(os.listdir(".")):
        if f.lower().endswith(VIDEO_EXT):
            print("Using video found in folder:", f)
            return f
    sys.exit("No video given. Use --input FILE or --url LINK (or put a video next to this script).")


def has_audio(src):
    out = sh(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
              "stream=index", "-of", "csv=p=0", src])
    return bool(out.strip())


def uid(name, kind):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "minevideo/%s/%s" % (name, kind)))


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def zipdirs(zpath, dirs):
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d in dirs:
            base = os.path.dirname(d)
            for root, _, files in os.walk(d):
                for fn in files:
                    p = os.path.join(root, fn)
                    z.write(p, os.path.relpath(p, base))


def main():
    ap = argparse.ArgumentParser(description="Video/link -> Minecraft Bedrock addon")
    ap.add_argument("--input", help="video file")
    ap.add_argument("--url", help="direct video link (or a page link if yt-dlp is installed)")
    ap.add_argument("--name", default="Video", help="addon name (letters and numbers)")
    ap.add_argument("--width", type=int, default=160, help="frame width in pixels (default 160)")
    ap.add_argument("--fps", type=int, default=8, help="frames per second (default 8)")
    ap.add_argument("--seconds", type=float, default=30, help="max length in seconds (default 30)")
    ap.add_argument("--start", type=float, default=0, help="start time in seconds")
    ap.add_argument("--loop", action="store_true", help="loop the picture (sound plays once)")
    ap.add_argument("--flip", action="store_true", help="mirror the picture horizontally")
    ap.add_argument("--no-audio", action="store_true", help="skip the sound")
    ap.add_argument("--out", default="out", help="output folder")
    args = ap.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(tool + " not found. Install ffmpeg first.")

    name = re.sub(r"[^A-Za-z0-9]", "", args.name) or "Video"
    out = os.path.abspath(args.out)
    work = os.path.join(out, "_work")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(work)

    src = pick_input(args, work)
    frames_dir = os.path.join(work, "frames")
    os.makedirs(frames_dir)

    print("Extracting frames ...")
    vf = "fps=%d,scale=%d:-2:flags=lanczos" % (args.fps, args.width)
    if args.flip:
        vf += ",hflip"
    sh(["ffmpeg", "-y", "-ss", str(args.start), "-t", str(args.seconds), "-i", src,
        "-vf", vf, "-an", os.path.join(frames_dir, "f%d.png")])
    files = sorted(glob.glob(os.path.join(frames_dir, "f*.png")),
                   key=lambda p: int(re.search(r"f(\d+)\.png", p).group(1)))
    n = len(files)
    if n < 2:
        sys.exit("No frames were produced. Check the video and the --start value.")
    w, h = png_size(files[0])
    seconds = round(n / float(args.fps), 2)
    print("Frames: %d  Size: %dx%d  Length: %.1fs" % (n, w, h, seconds))
    if n > 1200:
        print("WARNING: more than 1200 frames makes a heavy pack. Lower --fps, --width or --seconds.")

    audio_ok = False
    audio_path = os.path.join(work, "audio.ogg")
    if not args.no_audio and has_audio(src):
        print("Converting audio ...")
        base = ["ffmpeg", "-y", "-ss", str(args.start), "-t", str(args.seconds), "-i", src,
                "-vn", "-ac", "1", "-ar", "22050"]
        try:
            sh(base + ["-c:a", "libvorbis", "-q:a", "3", audio_path])
            audio_ok = True
        except SystemExit:
            print("libvorbis not available, sound skipped.")

    bp = os.path.join(out, "MineVideo_%s_BP" % name)
    rp = os.path.join(out, "MineVideo_%s_RP" % name)

    # ---------------- Resource pack ----------------
    tdir = os.path.join(rp, "textures", "video")
    os.makedirs(tdir)
    for i, p in enumerate(files):
        shutil.copy(p, os.path.join(tdir, "f%d.png" % i))
    textures = {"f%d" % i: "textures/video/f%d" % i for i in range(n)}

    write_json(os.path.join(rp, "manifest.json"), {
        "format_version": 2,
        "header": {"name": "MineVideo %s (resources)" % name,
                   "description": "Video frames and sound",
                   "uuid": uid(name, "rp"), "version": [1, 0, 0],
                   "min_engine_version": [1, 21, 0]},
        "modules": [{"type": "resources", "uuid": uid(name, "rpm"), "version": [1, 0, 0]}]
    })

    sw = 64.0
    sh_units = round(sw * h / float(w), 2)
    face = {"uv": [0, 0], "uv_size": [w, h]}
    tiny = {"uv": [0, 0], "uv_size": [1, 1]}
    write_json(os.path.join(rp, "models", "entity", "screen.geo.json"), {
        "format_version": "1.12.0",
        "minecraft:geometry": [{
            "description": {"identifier": "geometry.vid_screen", "texture_width": w, "texture_height": h,
                            "visible_bounds_width": 16, "visible_bounds_height": 10,
                            "visible_bounds_offset": [0, 0, 0]},
            "bones": [{"name": "screen", "pivot": [0, 0, 0], "cubes": [{
                "origin": [-sw / 2, -sh_units / 2, -0.5], "size": [sw, sh_units, 1],
                "uv": {"north": face, "south": face, "east": tiny, "west": tiny, "up": tiny, "down": tiny}
            }]}]
        }]
    })

    idx = "math.floor(query.life_time * %d)" % args.fps
    if args.loop:
        idx = "math.mod(%s, %d)" % (idx, n)
    else:
        idx = "math.min(%s, %d)" % (idx, n - 1)
    write_json(os.path.join(rp, "render_controllers", "screen.render_controllers.json"), {
        "format_version": "1.8.0",
        "render_controllers": {"controller.render.vid_screen": {
            "arrays": {"textures": {"Array.frames": ["Texture.f%d" % i for i in range(n)]}},
            "geometry": "Geometry.default",
            "materials": [{"*": "Material.default"}],
            "textures": ["Array.frames[%s]" % idx]
        }}
    })

    desc = {
        "identifier": "vid:screen",
        "materials": {"default": "entity_alphatest"},
        "textures": textures,
        "geometry": {"default": "geometry.vid_screen"},
        "render_controllers": ["controller.render.vid_screen"],
        "spawn_egg": {"base_color": "#111111", "overlay_color": "#ff3366"}
    }
    if audio_ok:
        desc["animations"] = {"play": "animation.vid.play"}
        desc["scripts"] = {"animate": ["play"]}
        desc["sound_effects"] = {"vid_audio": "vid.audio"}
        write_json(os.path.join(rp, "animations", "screen.animation.json"), {
            "format_version": "1.8.0",
            "animations": {"animation.vid.play": {
                "loop": False, "animation_length": seconds + 1,
                "sound_effects": {"0.0": {"effect": "vid_audio"}}}}
        })
        os.makedirs(os.path.join(rp, "sounds", "video"))
        shutil.copy(audio_path, os.path.join(rp, "sounds", "video", "audio.ogg"))
        write_json(os.path.join(rp, "sounds", "sound_definitions.json"), {
            "format_version": "1.14.0",
            "sound_definitions": {"vid.audio": {
                "category": "neutral", "min_distance": 6.0, "max_distance": 48.0,
                "sounds": [{"name": "sounds/video/audio", "stream": True, "volume": 1.0}]}}
        })
    write_json(os.path.join(rp, "entity", "screen.entity.json"),
               {"format_version": "1.10.0", "minecraft:client_entity": {"description": desc}})

    # ---------------- Behavior pack ----------------
    sizes = {"s": 0.5, "m": 1.0, "l": 2.0, "xl": 3.0}
    groups = {"vid:" + k: {"minecraft:scale": {"value": v}} for k, v in sizes.items()}
    events = {}
    for k in sizes:
        others = ["vid:" + o for o in sizes if o != k]
        events["vid:size_" + k] = {"remove": {"component_groups": others},
                                   "add": {"component_groups": ["vid:" + k]}}
    write_json(os.path.join(bp, "entities", "screen.json"), {
        "format_version": "1.16.0",
        "minecraft:entity": {
            "description": {"identifier": "vid:screen", "is_spawnable": True, "is_summonable": True},
            "component_groups": groups,
            "components": {
                "minecraft:type_family": {"family": ["vid_screen"]},
                "minecraft:collision_box": {"width": 0.1, "height": 0.1},
                "minecraft:physics": {"has_gravity": False, "has_collision": False},
                "minecraft:pushable": {"is_pushable": False, "is_pushable_by_piston": False},
                "minecraft:health": {"value": 1000, "max": 1000},
                "minecraft:persistent": {}
            },
            "events": events
        }
    })
    write_json(os.path.join(bp, "manifest.json"), {
        "format_version": 2,
        "header": {"name": "MineVideo %s (behavior)" % name,
                   "description": "Use a Clock to open the video menu",
                   "uuid": uid(name, "bp"), "version": [1, 0, 0],
                   "min_engine_version": [1, 21, 0]},
        "modules": [
            {"type": "data", "uuid": uid(name, "bpd"), "version": [1, 0, 0]},
            {"type": "script", "language": "javascript", "uuid": uid(name, "bps"),
             "entry": "scripts/main.js", "version": [1, 0, 0]}
        ],
        "dependencies": [
            {"uuid": uid(name, "rp"), "version": [1, 0, 0]},
            {"module_name": "@minecraft/server", "version": "1.19.0"},
            {"module_name": "@minecraft/server-ui", "version": "1.3.0"}
        ]
    })
    os.makedirs(os.path.join(bp, "scripts"), exist_ok=True)
    shutil.copy(os.path.join(HERE, "main.js"), os.path.join(bp, "scripts", "main.js"))
    with open(os.path.join(bp, "scripts", "config.js"), "w", encoding="utf-8") as f:
        f.write("export const VIDEO = %s;\n" % json.dumps(
            {"title": name, "seconds": seconds, "frames": n, "fps": args.fps,
             "width": w, "height": h, "audio": audio_ok, "loop": bool(args.loop)}))

    # ---------------- Icons ----------------
    try:
        from PIL import Image
        im = Image.open(files[0]).convert("RGB")
        side = min(im.size)
        l, t = (im.width - side) // 2, (im.height - side) // 2
        icon = im.crop((l, t, l + side, t + side)).resize((256, 256))
        icon.save(os.path.join(rp, "pack_icon.png"))
        icon.save(os.path.join(bp, "pack_icon.png"))
    except Exception:
        pass

    # ---------------- Package ----------------
    shutil.rmtree(work, ignore_errors=True)
    addon = os.path.join(out, "MineVideo_%s.mcaddon" % name)
    zipdirs(addon, [bp, rp])
    size_mb = os.path.getsize(addon) / 1048576.0
    print("\nDone: %s  (%.1f MB)" % (addon, size_mb))
    print("Open the .mcaddon file with Minecraft, add both packs to a world, hold a Clock and use it.")


if __name__ == "__main__":
    main()
