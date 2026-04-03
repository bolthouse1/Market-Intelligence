"""Voice interface — TTS via edge-tts, STT via SpeechRecognition."""

import asyncio
import logging
import os
import tempfile
from pathlib import Path

import edge_tts
import pygame
import speech_recognition as sr

logger = logging.getLogger(__name__)

# Default voice — sharp, natural male voice
DEFAULT_VOICE = "en-US-GuyNeural"
VOICE_RATE = "+5%"  # Slightly faster than default for that briefing energy

# Initialize pygame mixer for audio playback
pygame.mixer.init()


def set_voice(voice_name: str) -> None:
    """Change the TTS voice."""
    global DEFAULT_VOICE
    DEFAULT_VOICE = voice_name
    logger.info(f"Voice set to {voice_name}")


async def _generate_speech(text: str, output_path: str, voice: str | None = None) -> None:
    """Generate speech audio file from text using edge-tts."""
    v = voice or DEFAULT_VOICE
    communicate = edge_tts.Communicate(text, v, rate=VOICE_RATE)
    await communicate.save(output_path)


def speak(text: str, voice: str | None = None) -> None:
    """Convert text to speech and play it.

    Args:
        text: The text to speak.
        voice: Optional voice override.
    """
    # Strip markdown formatting for cleaner speech
    clean_text = _clean_for_speech(text)

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        temp_path = f.name

    try:
        asyncio.run(_generate_speech(clean_text, temp_path, voice))
        _play_audio(temp_path)
    except Exception as e:
        logger.error(f"TTS failed: {e}")
        # Fallback: just print the text
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
        pygame.time.wait(100)
    pygame.mixer.music.unload()


def listen(timeout: int = 10, phrase_time_limit: int = 30) -> str | None:
    """Listen for speech via microphone and return transcribed text.

    Args:
        timeout: Seconds to wait for speech to start.
        phrase_time_limit: Max seconds of speech to capture.

    Returns:
        Transcribed text, or None if nothing was heard.
    """
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 1.5  # Allow natural pauses

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
    """Strip markdown and formatting artifacts for cleaner TTS."""
    import re
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
    # Clean up multiple spaces/newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()
