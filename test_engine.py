"""Pruebas reproducibles del motor; sin datos externos ni servicios en la nube."""
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from engine import (Clip, ClipError, SpeechSegment, _split_caption, audio_energy,
                    duration_for, find_clips, is_youtube_url, render_clip,
                    save_project, subtitle_time, write_srt)


class MotorTests(unittest.TestCase):
    def test_youtube_links(self):
        self.assertTrue(is_youtube_url('https://youtu.be/abc123'))
        self.assertTrue(is_youtube_url('https://www.youtube.com/watch?v=abc123'))
        self.assertFalse(is_youtube_url('https://youtube.com.evil.test/watch?v=x'))
        self.assertFalse(is_youtube_url('file:///etc/passwd'))
        self.assertFalse(is_youtube_url('https://vimeo.com/123'))

    def test_invalid_parameters(self):
        with self.assertRaises(ClipError):
            find_clips('bad.mp4', 30, 90, 16, 'base')
        with self.assertRaises(ClipError):
            find_clips('bad.mp4', 90, 30, 15, 'base')
        with self.assertRaises(ClipError):
            find_clips('bad.mp4', 30, 90, 15, 'invalid')

    def test_timecode_and_subtitle(self):
        self.assertEqual(subtitle_time(61.503), '00:01:01,503')
        self.assertEqual(subtitle_time(-5), '00:00:00,000')
        with tempfile.TemporaryDirectory() as temp:
            dest = str(Path(temp) / 'sub.srt')
            count = write_srt(dest, Clip(10, 30, 1, '', ''), [
                SpeechSegment(6, 12, 'Esto es importante'),
                SpeechSegment(12, 17, 'No olvides tus impuestos'),
                SpeechSegment(31, 34, 'Fuera del fragmento')])
            self.assertEqual(count, 2)
            data = Path(dest).read_text()
            self.assertIn('00:00:00,000 --> 00:00:02,000', data)
            self.assertNotIn('Fuera', data)

    def test_project_file(self):
        with tempfile.TemporaryDirectory() as temp:
            save_project(temp, 'source.mp4', [Clip(1, 31, 10, 'Titular', 'ritmo')],
                         [SpeechSegment(1, 2, 'Hola')])
            data = json.loads((Path(temp) / 'proyecto_comunicando_clips.json').read_text())
            self.assertEqual(data['clips'][0]['status'], 'pendiente')
            self.assertEqual(data['segments'][0]['text'], 'Hola')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Requiere FFmpeg')
    def test_subtitles_and_blur(self):
        with tempfile.TemporaryDirectory() as td:
            source = str(Path(td) / 'original.mp4')
            output = str(Path(td) / 'subtitulado.mp4')
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                            '-f', 'lavfi', '-i', 'color=c=yellow:s=320x180:r=15:d=2',
                            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                            '-shortest', source], check=True)
            render_clip(source, Clip(0, 1.4, 2, 'Texto', 'Texto'),
                        [SpeechSegment(0.2, 1.1, 'Hola mundo')], output,
                        subtitle=True, layout='difuminado')
            self.assertGreater(Path(output).stat().st_size, 1000)
            with self.assertRaises(ClipError):
                render_clip(source, Clip(0, 1.4, 2, 'Texto', 'Texto'), [], output)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Requiere FFmpeg')
    def test_end_to_end_ffmpeg(self):
        with tempfile.TemporaryDirectory() as td:
            source = str(Path(td) / 'original.mp4')
            output = str(Path(td) / 'clip-vertical.mp4')
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                            '-f', 'lavfi', '-i', 'color=c=blue:s=320x180:r=15:d=3',
                            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000:duration=3',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                            '-shortest', source], check=True)
            self.assertAlmostEqual(duration_for(source), 3, delta=.2)
            self.assertGreater(len(audio_energy(source, 3)), 1)
            render_clip(source, Clip(0.1, 2.1, 4.0, 'Prueba', 'Prueba'), [], output,
                        subtitle=False, layout='recortar')
            self.assertTrue(Path(output).exists())
            self.assertGreater(Path(output).stat().st_size, 1000)
            probe = subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
                                    '-show_entries','stream=width,height', '-of','csv=p=0', output],
                                   check=True, capture_output=True, text=True)
            self.assertEqual(probe.stdout.strip(), '1080,1920')
            self.assertAlmostEqual(duration_for(output), 2, delta=.35)


if __name__ == '__main__':
    unittest.main()
