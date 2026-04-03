"""Voice interface — ElevenLabs TTS (primary), edge-tts (fallback), STT via SpeechRecognition.

Streams audio for fast response — starts speaking before the full text is generated.
"""

import asyncio
import io
import logging
import os
import re
import tempfile
import threading

import pygame
import speech_recognition as sr

logger = logging.getLogger(__name__)

# ElevenLabs config
ELEVEN_VOICE_ID = "iP95p4xoKVk53GoZ742B"  # "Chris" — charming, down-to-earth, casual
ELEVEN_MODEL = "eleven_turbo_v2_5"  # Fastest model — ~2-3x faster than multilingual_v2
ELEVEN_SPEED = 1.2  # Quick but natural

# Edge-tts fallback config
EDGE_VOICE = "en-US-GuyNeural"
EDGE_RATE = "+5%"

# Initialize pygame mixer
pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=2048)


def set_eleven_voice(voice_id: str) -> None:
    """Change the ElevenLabs voice ID."""
    global ELEVEN_VOICE_ID
    ELEVEN_VOICE_ID = voice_id
    logger.info(f"ElevenLabs voice set to {voice_id}")


def _has_eleven_key() -> bool:
    """Check if ElevenLabs API key is available."""
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def speak(text: str) -> None:
    """Convert text to speech and play it. Uses ElevenLabs if available, edge-tts as fallback."""
    clean_text = _clean_for_speech(text)

    if _has_eleven_key():
        try:
            _speak_eleven(clean_text)
            return
        except Exception as e:
            logger.warning(f"ElevenLabs failed, falling back to edge-tts: {e}")

    _speak_edge(clean_text)


def speak_streamed(text_chunks: list[str]) -> None:
    """Speak text in chunks — starts audio on first chunk while rest generates.

    This is the key to feeling fast: Andrew hears the first sentence
    within 1-2 seconds while the rest of the response is still being built.
    """
    if not _has_eleven_key():
        # Edge-tts doesn't stream well, so just concatenate and speak
        speak("\n".join(text_chunks))
        return

    for chunk in text_chunks:
        clean = _clean_for_speech(chunk)
        if clean.strip():
            try:
                _speak_eleven(clean)
            except Exception as e:
                logger.warning(f"Streamed chunk failed: {e}")
                print(chunk)


def _speak_eleven(text: str) -> None:
    """Generate and play speech via ElevenLabs."""
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

    # Generate audio with voice settings for natural delivery
    from elevenlabs import VoiceSettings
    audio_gen = client.text_to_speech.convert(
        voice_id=ELEVEN_VOICE_ID,
        text=text,
        model_id=ELEVEN_MODEL,
        output_format="mp3_44100_128",
        voice_settings=VoiceSettings(
            stability=0.4,          # Lower = more expressive, less robotic
            similarity_boost=0.75,  # Keep the voice character
            style=0.35,             # Add some style/energy
            use_speaker_boost=True,
        ),
    )

    # Collect the streamed bytes
    audio_bytes = b"".join(audio_gen)

    # Play via pygame
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio_bytes)
        temp_path = f.name

    try:
        _play_audio(temp_path)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def _speak_edge(text: str) -> None:
    """Fallback: generate and play speech via edge-tts."""
    import edge_tts

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        temp_path = f.name

    try:
        communicate = edge_tts.Communicate(text, EDGE_VOICE, rate=EDGE_RATE)
        asyncio.run(communicate.save(temp_path))
        _play_audio(temp_path)
    except Exception as e:
        logger.error(f"Edge-TTS failed: {e}")
        print(text)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def _play_audio(path: str) -> None:
    """Play an audio file and wait for it to finish."""
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.wait(50)
    pygame.mixer.music.unload()


def listen(timeout: int = 10, phrase_time_limit: int = 30) -> str | None:
    """Listen for speech via microphone and return transcribed text."""
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 1.5

    try:
        with sr.Microphone() as source:
            print("  [listening...]")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(
                source, timeout=timeout, phrase_time_limit=phrase_time_limit
            )

        print("  [processing...]")
        text = recognizer.recognize_google(audio)
        logger.info(f"Heard: {text}")
        return text

    except sr.WaitTimeoutError:
        logger.debug("No speech detected within timeout")
        return None
    except sr.UnknownValueError:
        logger.debug("Could not understand audio")
        return None
    except sr.RequestError as e:
        logger.error(f"Speech recognition service error: {e}")
        return None
    except Exception as e:
        logger.error(f"Microphone error: {e}")
        return None


def _clean_for_speech(text: str) -> str:
    """Strip markdown and formatting for cleaner, more natural TTS."""
    # Remove markdown bold/italic
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    # Remove markdown headers
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    # Remove bullet points but keep the text
    text = re.sub(r"^[-•]\s+", "", text, flags=re.MULTILINE)
    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)
    # Clean up currency symbols for better pronunciation
    text = text.replace("€", " euros")
    text = text.replace("£", " pounds")
    # Make "Braaah" sound right — like "bruh" but drawn out, the way kids say it
    text = re.sub(r"Braaah?", "Bruhhhhh", text, flags=re.IGNORECASE)
    # Add natural pauses after big numbers (helps pacing)
    text = re.sub(r"(\$[\d,.]+\s*(?:billion|million|trillion|B|M))", r"\1.", text)
    # Clean up multiple spaces/newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()
