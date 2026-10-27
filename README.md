# Modular AI Video Production Studio

A decoupled, modular AI video generation system designed to transform **any natural language prompt** into a dynamic 15–30 second 1080p video with character continuity, multi-character voice synthesis, and cinematic subtitles.

Every module can run **standalone** or coordinated through the unified **pipeline**.

---

## 📁 Project Architecture & Output Routing

```text
├── script/           # Standalone screenwriter & character DNA storyboard generator
│   └── output/       # script_<timestamp>.json + execution.log
├── voice/            # Standalone multi-character TTS synthesizer (Edge TTS)
│   └── output/       # voice_<timestamp>.mp3 or session_<timestamp>/ + execution.log
├── images/           # Standalone anime diffusion (CagliostroLab Animagine XL 3.1)
│   └── output/       # img_<timestamp>.jpg + execution.log
├── video/            # Standalone compositor (Ken Burns motion, subtitles & AI SVD)
│   └── output/       # video_<timestamp>.mp4 + execution.log
├── pipeline/         # End-to-end coordinator (script -> voice -> images -> video)
├── output/           # Coordinated pipeline session artifacts:
│   └── <name>_<timestamp>/
│       ├── script.json
│       ├── audio/
│       ├── images/
│       ├── segments/
│       ├── final_video.mp4
│       └── pipeline.log
└── logger.py         # Structured observability logger (timestamps, metrics & run logs)
```

---

## 🚀 Standalone Usage (Use Any Module Alone)

### 1. `script/` (Screenplay & Character Visual Bible)
Generates 4–6 lines of dialogue, character archetypes, camera framing, and immutable visual DNA sheets for **any** query:
```bash
python script/main.py "two rival detectives arguing in a rain-soaked alley"
# Output -> script/output/script_<timestamp>.json
```

### 2. `voice/` (Multi-Voice Synthesizer)
Synthesizes speech using Edge TTS dynamic casting (300+ voices, 44.1kHz stereo audio):
```bash
# Single voice line:
python voice/main.py "Hey there! Ready whenever you are."

# Or synthesize an entire script.json:
python voice/main.py --script script/output/script_<timestamp>.json
# Output -> voice/output/
```

### 3. `images/` (Animagine XL 3.1 Diffusion)
High-quality anime image generation powered by CagliostroLab's Animagine XL 3.1 (with NSFW/revealing outfit support):
```bash
python images/main.py "1girl, hatsune miku in sexy outfit, 16:9, masterpiece"
# Output -> images/output/img_<timestamp>.jpg
```

### 4. `video/` (Cinematic Compositor & AI Video)
Animates images with Ken Burns camera movement, styled subtitles, and 44.1kHz stereo audio:
```bash
# High-speed local Ken Burns compositor:
python video/main.py --image "images/output/img_<timestamp>.jpg" --audio "voice/output/voice_<timestamp>.mp3" --speaker "MIKU" --text "Let's make something amazing!"

# Or with Stable Video Diffusion AI Space:
python video/main.py --image "images/output/img_<timestamp>.jpg" --audio "voice/output/voice_<timestamp>.mp3" --engine ai_svd
# Output -> video/output/video_<timestamp>.mp4
```

---

## ⚡ Full End-to-End Pipeline

Run the complete pipeline from a single command for **any** query:
```bash
python pipeline/main.py "Two cyberpunk hackers breaking into a corporate vault"
```
Or interactively:
```bash
python pipeline/main.py
```

### Pipeline Flow:
1. **Script Engine**: Generates character visual DNA, scene atmosphere, and 15–30s script.
2. **Voice Engine**: Dynamically casts gender & age appropriate voices, rendering loud 44.1kHz stereo audio.
3. **Image Engine**: Synthesizes 16:9 keyframes with character continuity.
4. **Video Engine**: Adds camera pan/zoom motion, renders glowing dialogue nameplates and subtitles, and stitches everything into `output/<name>_<timestamp>/final_video.mp4`.
5. **Observability**: Complete step timing and execution metrics logged to `output/<name>_<timestamp>/pipeline.log`.
