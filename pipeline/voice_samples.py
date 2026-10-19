"""Voice samples for the language channels (Chatterbox Multilingual, MIT licence), for Charlie to pick a voice per language.

usage: python pipeline/voice_samples.py <out dir> [es pt ...]
Writes <lang>_<voice>.mp3 for each language: the model's own voice, and our two narrators (George, Emma) speaking the
language. A cloned English voice can carry an English accent; a lower cfg weight keeps less of it.
"""
import pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
TEXT = {
    "es": "Roman Reigns es Akuma en la nueva película de Street Fighter. Se estrenó el viernes en Estados Unidos, "
          "y el reparto es enorme. ¿Cuál es tu luchador favorito?",
    "pt": "Roman Reigns é o Akuma no novo filme de Street Fighter. A estreia foi na sexta-feira nos Estados Unidos, "
          "e o elenco é enorme. Qual é o seu lutador favorito?",
}
VOICES = {"default": None, "george": HERE / "voices" / "george_ref.wav", "emma": HERE / "voices" / "emma_ref.wav"}


def main(out, langs):
    import torch, torchaudio
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    torch.manual_seed(1)
    model = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
    out.mkdir(parents=True, exist_ok=True)
    for lang in langs:
        for name, ref in VOICES.items():
            kw = {"language_id": lang}
            if ref: kw.update(audio_prompt_path=str(ref), cfg_weight=0.3, exaggeration=0.5)
            wav = model.generate(TEXT[lang], **kw)
            tmp = out / f"{lang}_{name}.wav"
            torchaudio.save(str(tmp), wav, model.sr)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp), "-b:a", "96k", str(tmp.with_suffix(".mp3"))], check=True)
            tmp.unlink()
            print(lang, name, "done")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]), sys.argv[2:] or list(TEXT))
