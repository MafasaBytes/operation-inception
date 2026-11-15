"""One directed Pressure Bloom review: audit first, then consume frozen truth."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

from .pressure_audio import synthesize, write_wav
from .pressure_presentation import FrozenTape, PressureRenderer, canonical, sha

NAMES = tuple(f"ms06.3-{suffix}" for suffix in (
    "review.mp4", "muted.mp4", "contact-sheet.png", "audio.wav", "timeline.json",
    "robustness.json", "manifest.json"))


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def freeze_audited(cfg, report, result, config_file_hash):
    if not report["passed"]:
        raise ValueError("Robustness gate failed: rendering prohibited")
    sim = result.to_dict()
    if sha(cfg) != report["scenario_sha256"] or sha(sim) != report["results"][0]["simulation_sha256"]:
        raise ValueError("Audited input or simulation changed")
    duration = math.ceil((sim["final"]["time"]+.6)*30)/30
    return {"schema":"ms06.3.frozen-timeline.v1","rules":"PB-1.1","configuration":cfg,
            "configuration_file_sha256":config_file_hash,"scenario_sha256":sha(cfg),
            "simulation_sha256":sha(sim),"event_sha256":sha(sim["events"]),"simulation":sim,
            "presentation":{"fps":30,"width":720,"height":1280,"duration":duration,
                            "frame_count":round(duration*30),"unchanged_hold":duration-sim["final"]["time"],
                            "mapping":"one-to-one absolute seconds; no presentation stretching"},
            "status":"owner-and-wife normal-speed phone review pending"}


def encode_muted(renderer, path):
    args = ['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24',
            '-s:v','720x1280','-r','30','-i','pipe:0','-an','-c:v','libx264',
            '-vf','scale=in_range=pc:out_range=tv:out_color_matrix=bt709',
            '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',
            '-preset','slow','-threads','2','-profile:v','high','-pix_fmt','yuv420p','-crf','17',
            '-g','30','-movflags','+faststart',str(path)]
    proc = subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        for i in range(renderer.tape.frame_count):
            proc.stdin.write(renderer.render(i/30).tobytes())
            if i % 90 == 0:
                print(f'PB render {i}/{renderer.tape.frame_count}',flush=True)
        proc.stdin.close()
        error = proc.stderr.read()
        if proc.wait():
            raise RuntimeError(error.decode(errors='replace'))
    finally:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
        if proc.poll() is None:
            proc.terminate()
            proc.wait()


def video_stream_hash(path):
    result = subprocess.run(['ffmpeg','-v','error','-i',str(path),'-map','0:v:0','-c','copy',
                             '-f','h264','-'],capture_output=True,check=True)
    return hashlib.sha256(result.stdout).hexdigest()


def inspect_media(path):
    probe = subprocess.run(['ffprobe','-v','error','-show_entries',
                            'format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,duration,pix_fmt,color_space,color_transfer,color_primaries,sample_rate,channels',
                            '-of','json',str(path)],capture_output=True,text=True,check=True)
    subprocess.run(['ffmpeg','-v','error','-xerror','-err_detect','explode','-i',str(path),
                    '-f','null','-'],capture_output=True,check=True)
    data = json.loads(probe.stdout)
    v = next(s for s in data['streams'] if s['codec_type']=='video')
    if (v['width'],v['height'],v['r_frame_rate']) != (720,1280,'30/1'):
        raise ValueError('Incorrect review dimensions/FPS')
    if any(v[k]!='bt709' for k in ('color_space','color_transfer','color_primaries')):
        raise ValueError('Missing explicit BT.709 metadata')
    return {'probe':data,'full_decode':'passed','video_stream_sha256':video_stream_hash(path)}


def contact_sheet(renderer, path):
    times = (0.,1.25,3.7,6.3,10.5,14.65)
    sheet = Image.new('RGB',(1152,1410),(8,13,25))
    d = ImageDraw.Draw(sheet)
    try:
        font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18)
    except OSError:
        font=ImageFont.load_default()
    d.text((24,18),'MS06.3 / DIRECTED PRESSURE BLOOM / REVIEW SPOILERS',fill=(220,232,240),font=font)
    for i,t in enumerate(times):
        x,y=24+(i%3)*372,64+(i//3)*668
        sheet.paste(renderer.render(t).resize((360,640),Image.Resampling.LANCZOS),(x,y))
        d.text((x,y+643),f'{t:.2f}s',fill=(195,217,230),font=font)
    sheet.save(path)
    return times


def render_frozen(config_path: Path, output: Path):
    """No simulation call: render only the hash-verified already-audited tape."""
    audit_path=output/NAMES[5]
    timeline_path=output/NAMES[4]
    report=json.loads(audit_path.read_text())
    record=json.loads(timeline_path.read_text())
    if not report['passed'] or not all(report['gate'].values()):
        raise ValueError('Robustness gate failed; no render')
    if (file_hash(config_path)!=record['configuration_file_sha256']
        or report['scenario_sha256']!=record['scenario_sha256']
        or report['results'][0]['simulation_sha256']!=record['simulation_sha256']):
        raise ValueError('Frozen scenario/audit/timeline mismatch')
    for name in (NAMES[0],NAMES[1],NAMES[2],NAMES[3],NAMES[6]):
        if (output/name).exists():
            raise FileExistsError(f'Preserve existing prototype artifact: {output/name}')
    timeline_hash=file_hash(timeline_path)
    tape=FrozenTape.from_record(record)
    renderer=PressureRenderer(tape)
    with tempfile.TemporaryDirectory(prefix='.ms06.3-',dir=output) as temp:
        stage=Path(temp)
        encode_muted(renderer,stage/NAMES[1])
        pcm,audio=synthesize(tape.events,tape.duration)
        write_wav(stage/NAMES[3],pcm)
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(stage/NAMES[1]),
                        '-i',str(stage/NAMES[3]),'-c:v','copy','-c:a','aac','-b:a','192k',
                        '-t',f'{tape.duration:.9f}','-movflags','+faststart',str(stage/NAMES[0])],check=True)
        times=contact_sheet(renderer,stage/NAMES[2])
        probes={name:inspect_media(stage/name) for name in NAMES[:2]}
        if probes[NAMES[0]]['video_stream_sha256']!=probes[NAMES[1]]['video_stream_sha256']:
            raise ValueError('Review/muted encoded video differs')
        for name,media in probes.items():
            v=next(s for s in media['probe']['streams'] if s['codec_type']=='video')
            if int(v['nb_frames'])!=tape.frame_count:
                raise ValueError('Incorrect encoded frame count')
        if file_hash(timeline_path)!=timeline_hash or file_hash(config_path)!=record['configuration_file_sha256']:
            raise ValueError('Frozen truth changed during rendering')
        sim=record['simulation'];final=sim['final'];base=report['results'][0]
        manifest={'schema':'ms06.3.review-manifest.v1','rules':'PB-1.1',
                  'status':'owner-and-wife normal-speed phone review pending',
                  'provenance':'directed PB-1.1 prototype; authored initial scenario, not automatically generated candidate',
                  'scenario_sha256':record['scenario_sha256'],
                  'configuration_file_sha256':record['configuration_file_sha256'],
                  'simulation_sha256':tape.simulation_sha256,'event_sha256':tape.event_sha256,
                  'outcome':final['outcome'],'terminal_reason':final['reason'],'terminal_time':final['time'],
                  'first_contact':final['first_contact'],'event_times':base['event_times'],
                  'event_counts':base['event_counts'],'peak_live_count':base['peak_live_count'],
                  'initial_by_lineage':dict(Counter(b['lineage'] for b in sim['initial']['balls'])),
                  'initial_by_generation':dict(Counter(str(b['generation']) for b in sim['initial']['balls'])),
                  'final_by_lineage':base['final_by_lineage'],'final_by_generation':base['final_by_generation'],
                  'duration':tape.duration,'frame_count':tape.frame_count,'fps':30,'width':720,'height':1280,
                  'unchanged_hold':record['presentation']['unchanged_hold'],
                  'audio':audio,'media':probes,'contact_sheet_times':times,
                  'frame_sha256':{str(t):hashlib.sha256(renderer.render(t).tobytes()).hexdigest() for t in times},
                  'robustness':{'passed':report['passed'],'gate':report['gate'],
                                'probes':[{k:p[k] for k in ('probe','outcome','terminal_time','deterministic','finite','split_then_crush')}
                                          for p in report['results']]},
                  'source_sha256':{p.name:file_hash(p) for p in (config_path,
                       Path(__file__),Path(__file__).with_name('pressure_presentation.py'),
                       Path(__file__).with_name('pressure_audio.py'),Path(__file__).with_name('ms06_3_scenario.py'),
                       Path(__file__).with_name('pressure_bloom.py'))}}
        manifest['files']={name:{'sha256':file_hash((output if name in NAMES[4:6] else stage)/name),
                                 'bytes':((output if name in NAMES[4:6] else stage)/name).stat().st_size}
                           for name in NAMES[:-1]}
        (stage/NAMES[6]).write_text(json.dumps(manifest,indent=2)+'\n')
        for name in (*NAMES[:4],NAMES[6]):
            (stage/name).replace(output/name)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path('configs/ms06.3.json'))
    parser.add_argument('--output-dir',type=Path,default=Path('outputs/ms06.3'))
    parser.add_argument('--render-frozen',action='store_true',help='Reuse the completed audit/timeline; never resimulate')
    args=parser.parse_args()
    if not args.render_frozen:
        from .ms06_3_scenario import load_scenario,robustness_audit
        if any((args.output_dir/name).exists() for name in NAMES):
            raise FileExistsError('MS06.3 artifacts exist; preserve this review package')
        cfg=load_scenario(args.config)
        config_hash=file_hash(args.config)
        report,result=robustness_audit(cfg)
        if file_hash(args.config)!=config_hash:
            raise ValueError('Configuration changed during audit')
        report['configuration_file_sha256']=config_hash
        args.output_dir.mkdir(parents=True,exist_ok=True)
        (args.output_dir/NAMES[5]).write_text(canonical(report)+'\n')
        if not report['passed']:
            print('Robustness gate failed. Report preserved; rendering stopped.',flush=True)
            return
        record=freeze_audited(cfg,report,result,config_hash)
        (args.output_dir/NAMES[4]).write_text(canonical(record)+'\n')
    manifest=render_frozen(args.config,args.output_dir)
    print(f"MS06.3 ready for phone review: {manifest['duration']:.3f}s, {manifest['outcome']}",flush=True)


if __name__=='__main__':
    main()
