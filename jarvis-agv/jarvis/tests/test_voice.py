import asyncio
import io
import json
import sys
import types
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from jarvis import app
from jarvis import voice

# Catálogo esperado: só vozes masculinas, com o nome do próprio assistente.
EXPECTED = {
    "pt-BR": {"jarvis-pt": "pt-BR-AntonioNeural"},
    "en-US": {"jarvis-en": "en-GB-RyanNeural"},
}
# Ids que apareciam na interface antes e não devem voltar.
REMOVED = ("francisca", "jenny", "guy")


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.generated = []
        generated = self.generated

        async def list_voices():
            engines = [engine for profiles in EXPECTED.values() for engine in profiles.values()]
            engines += ["pt-BR-FranciscaNeural", "en-US-JennyNeural", "en-US-GuyNeural",
                        "pt-BR-ThalitaNeural", "en-US-AriaNeural", "es-ES-ElviraNeural"]
            return [{"ShortName": engine, "FriendlyName": "Microsoft Pessoa - " + engine}
                    for engine in engines]

        class Communicate:
            def __init__(self, text, engine, **options):
                generated.append((text, engine, options))

            async def stream(self):
                yield {"type": "audio", "data": b"ID3-test-audio"}

        edge = types.SimpleNamespace(list_voices=list_voices, Communicate=Communicate, exceptions=types.SimpleNamespace())
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {"edge_tts": edge}).start()
        patch.object(voice, "_AVAILABLE_ENGINES_CACHE", None).start()
        patch.object(voice, "_LIVE_VOICE_CACHE", {}).start()

    def test_catalog_only_offers_the_jarvis_male_voices(self):
        for language, profiles in EXPECTED.items():
            self.assertEqual(set(voice.CATALOG[language]["voices"]), set(profiles))
            for voice_id, engine in profiles.items():
                self.assertEqual(voice.CATALOG[language]["voices"][voice_id]["engine"], engine)
        self.assertEqual(voice.DEFAULT_VOICES, {"pt-BR": "jarvis-pt", "en-US": "jarvis-en"})

    def test_no_person_name_is_shown_to_the_user(self):
        rotulos = [item["label"] for data in voice.CATALOG.values() for item in data["voices"].values()]
        self.assertTrue(all(rotulo.startswith("Jarvis — ") for rotulo in rotulos), rotulos)
        texto = " ".join(rotulos).lower()
        for nome in ("antônio", "antonio", "francisca", "jenny", "guy", "ryan", "thomas"):
            self.assertNotIn(nome, texto)

    def test_live_catalog_keeps_our_labels_and_never_reintroduces_removed_voices(self):
        result = voice.catalog_for_client(live=True)
        self.assertEqual(set(result), set(EXPECTED))
        for language, expected in EXPECTED.items():
            self.assertEqual(set(result[language]["voices"]), set(expected))
            for rotulo in result[language]["voices"].values():
                self.assertTrue(rotulo.startswith("Jarvis — "), rotulo)
                self.assertNotIn("Microsoft", rotulo)
        todos = {v for data in result.values() for v in data["voices"]}
        for removida in REMOVED:
            self.assertNotIn(removida, todos)

    def test_each_selected_voice_reaches_its_engine(self):
        for language, profiles in EXPECTED.items():
            for selected, engine in profiles.items():
                with self.subTest(voice=selected):
                    result = asyncio.run(voice.synthesize("Teste.", language, selected))
                    self.assertEqual(result, b"ID3-test-audio")
                    self.assertEqual(self.generated[-1][1], engine)

    def test_old_saved_voice_ids_are_migrated_instead_of_failing(self):
        for language, antigo, engine in [
            ("pt-BR", "antonio", "pt-BR-AntonioNeural"),
            ("pt-BR", "francisca", "pt-BR-AntonioNeural"),
            ("en-US", "jenny", "en-GB-RyanNeural"),
            ("en-US", "guy", "en-GB-RyanNeural"),
        ]:
            with self.subTest(antigo=antigo):
                self.assertEqual(voice.resolve_voice_id(antigo, language),
                                 voice.DEFAULT_VOICES[language])
                with patch("builtins.print"):
                    asyncio.run(voice.synthesize("Teste.", language, antigo))
                self.assertEqual(self.generated[-1][1], engine)

    def test_unknown_or_missing_voice_uses_the_language_default(self):
        for language in EXPECTED:
            self.assertEqual(voice.resolve_voice_id(None, language), voice.DEFAULT_VOICES[language])
            self.assertEqual(voice.resolve_voice_id("inexistente", language), voice.DEFAULT_VOICES[language])
            self.assertEqual(voice.resolve_voice_id(123, language), voice.DEFAULT_VOICES[language])

    def test_default_pitch_is_lower_and_reaches_the_engine(self):
        self.assertEqual(voice.DEFAULT_PITCH, -4)
        asyncio.run(voice.synthesize("Teste.", "pt-BR", "jarvis-pt"))
        self.assertEqual(self.generated[-1][2]["pitch"], "-4Hz")

    def test_first_sentence_does_not_wait_for_the_voice_listing(self):
        """A consulta list_voices não entra no caminho da primeira fala."""
        chamadas = []

        async def lenta():
            chamadas.append(1)
            return [{"ShortName": "pt-BR-AntonioNeural"}]

        edge = sys.modules["edge_tts"]
        with patch.object(edge, "list_voices", lenta):
            asyncio.run(voice.synthesize("Teste.", "pt-BR", "jarvis-pt"))
        self.assertEqual(chamadas, [], "não deveria consultar o serviço antes de falar")
        self.assertEqual(self.generated[-1][1], "pt-BR-AntonioNeural")

    def test_warm_cache_still_catches_an_engine_the_service_removed(self):
        patch.object(voice, "_AVAILABLE_ENGINES_CACHE", {"pt-BR-AntonioNeural"}).start()
        patch.object(voice, "_AVAILABLE_ENGINES_AT", float("inf")).start()
        with self.assertRaises(voice.VoiceError) as erro:
            asyncio.run(voice.synthesize("Test.", "en-US", "jarvis-en"))
        self.assertEqual(erro.exception.code, "voice_unavailable")

    def test_spanish_cannot_generate_audio(self):
        with self.assertRaises(voice.VoiceError) as error:
            asyncio.run(voice.synthesize("Hola.", "es-ES", "elvira"))
        self.assertEqual(error.exception.code, "invalid_language")
        self.assertEqual(self.generated, [])

    def test_spanish_http_request_is_rejected_before_synthesis(self):
        handler = app.Handler.__new__(app.Handler)
        body = json.dumps({"texto": "Hola.", "idioma": "es-ES", "voz": "elvira"}).encode()
        handler.headers = Message()
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = io.BytesIO(body)
        with patch.object(handler, "send") as send, patch.object(voice, "synthesize") as synthesize:
            handler.tts()
        self.assertEqual(send.call_args.args[0], 400)
        self.assertEqual(send.call_args.args[1]["codigo"], "invalid_request")
        synthesize.assert_not_called()

    def test_http_request_without_a_voice_uses_the_default_and_lower_pitch(self):
        handler = app.Handler.__new__(app.Handler)
        body = json.dumps({"texto": "Olá.", "idioma": "pt-BR"}).encode()
        handler.headers = Message()
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = io.BytesIO(body)
        with patch.object(handler, "send") as send:
            handler.tts()
        self.assertEqual(send.call_args.args[0], 200)
        self.assertEqual(self.generated[-1][1], "pt-BR-AntonioNeural")
        self.assertEqual(self.generated[-1][2]["pitch"], "-4Hz")


if __name__ == "__main__":
    unittest.main()
