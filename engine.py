"""Motor local de Comunicando Clips (FFmpeg + Whisper opcional)."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from array import array
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse


class ClipError(Exception):
    pass


def ffmpeg_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for p in (f'/opt/homebrew/bin/{name}', f'/usr/local/bin/{name}'):
        if os.path.isfile(p):
            return p
    raise ClipError(f'No se encuentra {name}. Instala FFmpeg con: brew install ffmpeg')


def command(args: list[str], timeout: int | None = None) -> str:
    p = subprocess.run(args, capture_output=True, text=True, errors='replace', timeout=timeout)
    if p.returncode != 0:
        raise ClipError((p.stderr or p.stdout or 'Error desconocido')[-1600:])
    return p.stdout


def duration_for(path: str) -> float:
    out = command([ffmpeg_binary('ffprobe'), '-v', 'error', '-show_entries',
                   'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', path])
    try:
        d = float(out.strip())
    except ValueError as exc:
        raise ClipError('No se pudo leer la duración del video.') from exc
    if not math.isfinite(d) or d <= 0:
        raise ClipError('El video tiene una duración no válida.')
    return d


def is_youtube_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    domain = (parsed.hostname or '').lower().removeprefix('www.').removeprefix('m.')
    return parsed.scheme in ('http', 'https') and domain in ('youtube.com', 'youtu.be', 'youtube-nocookie.com')


def download_youtube(url: str, folder: str, notify=lambda _: None) -> str:
    if not is_youtube_url(url):
        raise ClipError('Introduce un enlace válido de YouTube o YouTube Shorts.')
    try:
        import yt_dlp
    except ImportError as exc:
        raise ClipError('Falta yt-dlp. Ejecuta nuevamente el instalador.') from exc
    notify('Descargando video de YouTube…')
    target = str(Path(folder) / '%(title).100B_%(id)s.%(ext)s')
    options = {
        'outtmpl': target,
        'format': 'bv*+ba/b',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'restrictfilenames': True,
        'paths': {'home': str(Path(folder).resolve())},
    }
    with yt_dlp.YoutubeDL(options) as dl:
        data = dl.extract_info(url, download=True)
        final = dl.prepare_filename(data)
    info_id = data.get('id') if isinstance(data, dict) else None
    candidates = [Path(final), Path(final).with_suffix('.mp4')]
    if info_id:
        candidates += list(Path(folder).glob(f'*_{info_id}.mp4'))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise ClipError('No se encontró el archivo descargado.')


@dataclass
class SpeechSegment:
    start: float
    end: float
    text: str


@dataclass
class Clip:
    start: float
    end: float
    score: float
    title: str
    reason: str
    status: str = 'pendiente'
    output: str = ''


HOT_WORDS = {
    'atención': 2, 'importante': 2, 'secreto': 2, 'nunca': 2, 'millones': 2,
    'dinero': 2, 'impuestos': 2, 'dólares': 2, 'trump': 1, 'bukele': 1,
    'economía': 2, 'última': 1, 'verdad': 2, 'increíble': 2, 'cómo': 1,
    'por qué': 2, 'sabías': 2, 'cuidado': 2, 'descubre': 2, 'ahora': 1,
    'familia': 1, 'crédito': 2, 'gobierno': 1, 'problema': 1,
    'beneficio': 2, 'riesgo': 2, 'revela': 2, 'resulta': 1,
    'warning': 2, 'important': 2, 'money': 2, 'taxes': 2,
    'secret': 2, 'why': 1, 'how': 1, 'breaking': 2,
}


def audio_energy(path: str, length: float, notify=lambda _: None) -> list[float]:
    """Energía RMS por segundo. No almacena el audio entero en RAM."""
    notify('Analizando ritmo y volumen de voz…')
    ff = ffmpeg_binary('ffmpeg')
    cmd = [ff, '-nostdin', '-loglevel', 'error', '-i', path, '-vn', '-ac', '1',
           '-ar', '2000', '-f', 's16le', 'pipe:1']
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    values = []
    try:
        while True:
            data = proc.stdout.read(4000)
            if not data:
                break
            if len(data) & 1:
                data = data[:-1]
            a = array('h')
            a.frombytes(data)
            if not a:
                break
            values.append(math.sqrt(sum(x*x for x in a) / len(a)) / 32768.0)
        proc.wait(timeout=20)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if proc.stdout is not None:
            proc.stdout.close()
    return values or [0.01] * max(1, math.ceil(length))


def transcribe(path: str, model_size: str, notify=lambda _: None) -> list[SpeechSegment]:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        notify('Whisper no está instalado: se analizará el audio sin transcripción.')
        return []
    notify('Cargando reconocimiento de voz (la primera vez puede descargar el modelo)…')
    try:
        model = WhisperModel(model_size, device='cpu', compute_type='int8', cpu_threads=min(os.cpu_count() or 4, 8))
        notify('Transcribiendo voz localmente…')
        iterator, _info = model.transcribe(path, beam_size=3, vad_filter=True,
                                            condition_on_previous_text=False)
        return [SpeechSegment(float(s.start), float(s.end), s.text.strip()) for s in iterator if s.text.strip()]
    except Exception as exc:
        notify('No se pudo transcribir; se utilizará el análisis de voz.')
        return []


def _mean_energy(values: list[float], a: float, b: float) -> float:
    x = max(0, min(len(values)-1, int(a)))
    y = max(x+1, min(len(values), math.ceil(b)))
    return sum(values[x:y]) / max(1, y-x)


def find_clips(path: str, minimum: int, maximum: int, count: int, model_size: str,
               notify=lambda _: None) -> tuple[list[Clip], list[SpeechSegment]]:
    if not 1 <= count <= 15 or minimum < 1 or maximum < minimum or maximum > 180:
        raise ClipError('Revisa la cantidad de clips y las duraciones solicitadas.')
    if model_size not in {'tiny', 'base', 'small'}:
        raise ClipError('Modelo de voz no reconocido.')
    d = duration_for(path)
    if d < minimum:
        raise ClipError(f'El video dura {d:.0f} segundos; el mínimo solicitado es {minimum}.')
    segments = transcribe(path, model_size, notify)
    volumes = audio_energy(path, d, notify)
    global_energy = max(0.001, sum(volumes)/len(volumes))
    candidates: list[Clip] = []
    target_durations = sorted(set([minimum, min(maximum, 45), min(maximum, 60), maximum]))
    if segments:
        starts = sorted(set([0] + [max(0, int(s.start)-2) for s in segments]))
    else:
        starts = list(range(0, max(1, int(d-minimum)+1), max(5, minimum//3)))
    notify('Buscando los momentos con más potencial…')
    for start in starts:
        for desired in target_durations:
            end = min(d, start + desired)
            if end - start < minimum - 0.05:
                continue
            local = [s for s in segments if s.end > start and s.start < end]
            joined = ' '.join(s.text.lower() for s in local)
            words = re.findall(r'\b[\wáéíóúñü]+\b', joined)
            hot = sum(weight for term, weight in HOT_WORDS.items() if term in joined)
            questions = joined.count('?') + joined.count('¿')
            numeric = len(re.findall(r'\b\d[\d.,]*\b', joined))
            energy = _mean_energy(volumes, start, end)
            speech = sum(max(0, min(end, s.end)-max(start, s.start)) for s in local)
            density = speech / max(1, end-start) if local else 0.6
            diversity = len(set(words))/max(1, len(words)) if words else 0.5
            score = (min(8, hot)*1.8 + min(4, questions)*1.2 + min(5, numeric)*0.7
                     + min(2.0, energy/global_energy)*3.0 + min(1.0, density)*4.0
                     + diversity*2 + min(5, len(words)/25) + (1 if local else 0))
            title = ' '.join(words[:7]).strip() if words else f'Momento destacado {int(start//60)+1}'
            title = title[:55].capitalize()
            reason = ('Frases de impacto y ritmo de voz' if hot else
                      'Voz activa y buen ritmo' if energy > global_energy else 'Fragmento potencial')
            candidates.append(Clip(round(start, 2), round(end, 2), round(score, 2), title, reason))
    candidates.sort(key=lambda c: c.score, reverse=True)
    chosen = []
    for clip in candidates:
        if any(max(0, min(clip.end, c.end)-max(clip.start, c.start)) /
               min(clip.end-clip.start, c.end-c.start) > 0.40 for c in chosen):
            continue
        chosen.append(clip)
        if len(chosen) >= count:
            break
    chosen.sort(key=lambda c: c.start)
    notify(f'{len(chosen)} fragmentos identificados. Revisa antes de guardar.')
    return chosen, segments


def subtitle_time(t: float) -> str:
    ms = int(max(0, t) * 1000)
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def _split_caption(txt: str, max_chars: int = 27) -> list[str]:
    words = txt.split()
    lines, line = [], ''
    for word in words:
        if len(line) + len(word) + bool(line) > max_chars:
            if line:
                lines.append(line)
            line = word
        else:
            line = f'{line} {word}'.strip()
    if line:
        lines.append(line)
    return lines


def write_srt(path: str, clip: Clip, segments: list[SpeechSegment]) -> int:
    entries = []
    for seg in segments:
        a = max(clip.start, seg.start)
        b = min(clip.end, seg.end)
        if b-a < 0.2:
            continue
        lines = _split_caption(seg.text)
        if not lines:
            continue
        # Dividir subtítulos largos en bloques de dos líneas.
        chunks = [lines[i:i+2] for i in range(0, len(lines), 2)]
        for index, chunk in enumerate(chunks):
            sa = a + (b-a)*index/len(chunks)
            sb = a + (b-a)*(index+1)/len(chunks)
            entries.append((sa-clip.start, sb-clip.start, '\n'.join(chunk)))
    with open(path, 'w', encoding='utf-8') as f:
        for i, (a, b, caption) in enumerate(entries, 1):
            f.write(f'{i}\n{subtitle_time(a)} --> {subtitle_time(b)}\n{caption}\n\n')
    return len(entries)


def render_clip(source: str, clip: Clip, segments: list[SpeechSegment], output: str,
                subtitle: bool = True, layout: str = 'recortar', notify=lambda _: None):
    if layout not in {'recortar', 'difuminado'}:
        raise ClipError('Modo de composición no válido.')
    if not (math.isfinite(clip.start) and math.isfinite(clip.end) and clip.end > clip.start >= 0):
        raise ClipError('Los tiempos del clip no son válidos.')
    if Path(output).exists():
        raise ClipError('Ya existe un archivo con ese nombre. No se sobrescribirá.')
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='comunicando_') as tmp:
        srt = str(Path(tmp) / 'subtitulos.srt')
        n = write_srt(srt, clip, segments) if subtitle else 0
        # Relación 9:16 para cualquier video; recorte central o fondo difuminado.
        if layout == 'difuminado':
            vf = ('[0:v]split=2[bg][fg];'
                  '[bg]scale=1080:1920:force_original_aspect_ratio=increase,'
                  'crop=1080:1920,boxblur=30:10[base];'
                  '[fg]scale=1080:1920:force_original_aspect_ratio=decrease[front];'
                  '[base][front]overlay=(W-w)/2:(H-h)/2,setsar=1[v]')
            filter_arg = ['-filter_complex', vf, '-map', '[v]', '-map', '0:a?']
        else:
            vf = 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1'
            filter_arg = ['-vf', vf]
        if n:
            # Aplicar subtítulos en una pasada separada: evita conflictos con filter_complex.
            raw = str(Path(tmp) / 'base.mp4')
        else:
            raw = output
        notify('Renderizando video vertical 1080 × 1920…')
        basecmd = [ffmpeg_binary('ffmpeg'), '-y', '-hide_banner', '-loglevel', 'error',
                   '-ss', str(clip.start), '-i', source, '-t', str(clip.end-clip.start),
                   *filter_arg, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22',
                   '-pix_fmt', 'yuv420p', '-r', '30', '-c:a', 'aac', '-b:a', '160k',
                   '-movflags', '+faststart', raw]
        command(basecmd)
        if n:
            notify('Agregando subtítulos en español…')
            # El SRT está en carpeta temporal sin caracteres especiales problemáticos.
            escaped = srt.replace('\\', '\\\\').replace(':', '\\:').replace("'", "\\'")
            style = 'FontName=Arial,FontSize=17,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=180'
            command([ffmpeg_binary('ffmpeg'), '-y', '-hide_banner', '-loglevel', 'error',
                     '-i', raw, '-vf', f"subtitles=filename='{escaped}':force_style='{style}'",
                     '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-c:a', 'copy',
                     '-movflags', '+faststart', output])
        if not Path(output).exists() or Path(output).stat().st_size == 0:
            raise ClipError('La exportación no produjo un video válido.')


def save_project(folder: str, video: str, clips: list[Clip], segments: list[SpeechSegment]):
    Path(folder).mkdir(parents=True, exist_ok=True)
    target = Path(folder) / 'proyecto_comunicando_clips.json'
    with target.open('w', encoding='utf-8') as f:
        json.dump({'video': video, 'clips': [asdict(c) for c in clips],
                   'segments': [asdict(s) for s in segments]}, f, ensure_ascii=False, indent=2)
