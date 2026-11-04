#!/usr/bin/env python3
"""Download two natural long-form recordings and references for local evaluation.

Only selected recordings are saved; archive traversal may transfer over 1GB per
language. No model download. Requires local ffmpeg. Audio/reference files must
remain outside Git and release archives. Source: espnet/yodas2, CC BY 3.0.
"""
import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REVISION = '631fc446cb1a41ee93a1d390a167c6e08c2597a3'
BASE = f'https://huggingface.co/datasets/espnet/yodas2/resolve/{REVISION}'
CASES = {'zh': ('1R_ektyh3oA', 'workplace management spoken presentation', 'ja'),
         'ja': ('Y0wyvkJ18U0', 'Japanese parliamentary questions and answers', 'zh')}


def download(language, directory):
    identifier, description, target = CASES[language]
    subset = f'{language}000'
    with urllib.request.urlopen(f'{BASE}/data/{subset}/text/00000000.json', timeout=90) as response:
        records = json.load(response)
    reference = next(record for record in records if record['audio_id'] == identifier)
    url = f'{BASE}/data/{subset}/audio/00000000.tar.gz'
    directory.mkdir(parents=True, exist_ok=True)
    original = directory / f'{language}-original.wav'
    with urllib.request.urlopen(url, timeout=90) as response, tarfile.open(fileobj=response, mode='r|gz') as archive:
        for index, member in enumerate(archive):
            print(f'{language}: scanning recording {index+1}: {member.name}', flush=True)
            if member.isfile() and Path(member.name).stem == identifier:
                with archive.extractfile(member) as audio, original.open('wb') as out:
                    while block := audio.read(1024 * 1024): out.write(block)
                break
        else:
            raise RuntimeError(f'Recording not found: {identifier}')
    converted = directory / f'{language}16.wav'
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(original),
                    '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', str(converted)], check=True)
    utterances = []
    for key, text in sorted(reference['text'].items()):
        fields = key.split('-')
        utterances.append(dict(start=int(fields[-2])/100, end=int(fields[-1])/100, text=text))
    manifest = dict(audio=str(converted.resolve()), language=language, target=target,
        source=dict(dataset='espnet/yodas2', revision=REVISION, subset=subset, shard='00000000',
                    identifier=identifier, description=description, archive_url=url, license='CC-BY-3.0',
                    attribution='Xinjian Li et al., YODAS (ASRU 2023); espnet/yodas2 contributors and original CC video creators',
                    original_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
                    pcm_wav_sha256=hashlib.sha256(converted.read_bytes()).hexdigest()),
        reference_kind='dataset_subtitles_not_independently_verified', utterances=utterances)
    path = directory / f'{language}-manifest.json'
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f'Ready: {path}', flush=True)


def download_meeting(directory):
    """Use only the first 32MiB of this official eight-channel FLAC."""
    directory.mkdir(parents=True, exist_ok=True)
    base = 'https://huggingface.co/datasets/AISHELL/AISHELL-4/resolve/main/test'
    audio_url = f'{base}/wav/S_R004S01C01.flac'
    reference_url = f'{base}/TextGrid/S_R004S01C01.TextGrid'
    with urllib.request.urlopen(reference_url, timeout=90) as response:
        annotation = response.read().decode('utf-8')
    partial = directory / 'zh-meeting-first32MiB.flac'
    request = urllib.request.Request(audio_url, headers={'Range': 'bytes=0-33554431'})
    with urllib.request.urlopen(request, timeout=90) as response, partial.open('wb') as out:
        remaining = 33554432
        while remaining:
            block = response.read(min(remaining, 1024 * 1024))
            if not block: break
            out.write(block)
            remaining -= len(block)
    converted = directory / 'zh-meeting16.wav'
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(partial),
        '-t', '180', '-af', 'pan=mono|c0=c0', '-ar', '16000', '-c:a', 'pcm_s16le', str(converted)], check=True)
    utterances = []
    for tier in re.split(r'\n    item \[\d+\]:', annotation)[1:]:
        speaker = re.search(r'name = "([^"]+)"', tier).group(1)
        for m in re.finditer(r'intervals \[\d+\]:\s+xmin = ([\d.]+)\s+xmax = ([\d.]+)\s+text = "([^"]*)"', tier):
            start, end = float(m[1]), float(m[2])
            text = re.sub(r'<[^>]+>', '', m[3]).strip()
            if text and end <= 180:
                utterances.append(dict(start=start, end=end, text=text, speaker=speaker))
    utterances.sort(key=lambda line: line['start'])
    manifest = dict(audio=str(converted.resolve()), language='zh', target='ja',
        source=dict(dataset='AISHELL/AISHELL-4', identifier='S_R004S01C01', channel=0,
            clip_seconds=180, license='CC-BY-SA-4.0', audio_url=audio_url, reference_url=reference_url,
            attribution='Yihui Fu et al., AISHELL-4 (Interspeech 2021); Beijing Shell Shell Technology Co., Ltd. and dataset contributors',
            partial_flac_sha256=hashlib.sha256(partial.read_bytes()).hexdigest(),
            pcm_wav_sha256=hashlib.sha256(converted.read_bytes()).hexdigest()),
        reference_kind='official_TextGrid_verbatim_annotations', utterances=utterances)
    path = directory / 'zh-meeting-manifest.json'
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f'Ready: {path}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=['zh', 'ja', 'zh-meeting', 'all'], default='all')
    parser.add_argument('--output-dir', type=Path, default=Path(tempfile.gettempdir())/'local-meeting-evaluation')
    args = parser.parse_args()
    selected = ['zh-meeting', 'ja', 'zh'] if args.language == 'all' else [args.language]
    for language in selected:
        if language == 'zh-meeting': download_meeting(args.output_dir)
        else: download(language, args.output_dir)
