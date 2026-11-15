"""Export this one PB-2.0 review from an already-frozen, gate-passing tape."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from PIL import Image,ImageDraw,ImageFont
from .capacity_presentation import Tape,Renderer,canonical,digest
from .capacity_audio import synthesize,write_wav
from .ms06_3 import encode_muted,inspect_media

NAMES=tuple('ms06.3d-'+s for s in ('review.mp4','muted.mp4','contact-sheet.png','audio.wav','timeline.json','robustness.json','manifest.json'))
ROOT=Path(__file__).resolve().parents[2]
SOURCES=('src/inception/capacity_bloom.py','src/inception/capacity_layout.py',
         'src/inception/ms06_pb2.py','src/inception/ms06_3d_scenario.py',
         'src/inception/capacity_presentation.py','src/inception/capacity_audio.py',
         'src/inception/ms06_3d.py','src/inception/pressure_audio.py','src/inception/ms06_3.py',
         'fixtures/ms06.3d/pb2-rules-v1.json','fixtures/ms06.3d/pb2-conformance-v1.json')


def file_hash(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def freeze_sources(config_path,output):
    """Finalize source provenance before rendering, without running simulation."""
    path=output/NAMES[4];r=json.loads(path.read_text())
    freeze={'configuration_file_sha256':file_hash(config_path),
            'robustness_file_sha256':file_hash(output/NAMES[5]),
            'conformance_file_sha256':file_hash(output/'ms06.3d-conformance-v1.json'),
            'source_sha256':{p:file_hash(ROOT/p) for p in SOURCES}}
    if 'freeze' in r:
        if r['freeze']!=freeze:raise ValueError('Frozen sources changed')
    else:
        r['freeze']=freeze;path.write_text(canonical(r)+'\n')
    return r


def render_frozen(config_path,output):
    for name in (*NAMES[:4],NAMES[6]):
        if (output/name).exists():raise FileExistsError('Preserve existing artifact: '+str(output/name))
    record=freeze_sources(config_path,output)
    report=json.loads((output/NAMES[5]).read_text());proof=json.loads((output/'ms06.3d-conformance-v1.json').read_text())
    if not report['passed'] or not all(report['gate'].values()) or not proof['passed']:raise ValueError('Pre-render gate failed')
    if (report['scenario_sha256']!=record['configuration_sha256'] or report['base']['simulation_sha256']!=record['simulation_sha256']
        or report['layout_sha256']!=record['layout_sha256'] or proof['rules_sha256']!=record['rules_sha256']):raise ValueError('Audit/freeze mismatch')
    if digest(json.loads(config_path.read_text()))!=record['configuration_sha256']:raise ValueError('Configuration changed')
    timeline_hash=file_hash(output/NAMES[4]);tape=Tape.from_record(record);renderer=Renderer(tape)
    with tempfile.TemporaryDirectory(prefix='.ms06.3d-',dir=output) as temporary:
        stage=Path(temporary)
        encode_muted(renderer,stage/NAMES[1])
        pcm,audio=synthesize(tape.events,tape.duration)
        write_wav(stage/NAMES[3],pcm)
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(stage/NAMES[1]),'-i',str(stage/NAMES[3]),
                        '-c:v','copy','-c:a','aac','-b:a','192k','-t',str(tape.duration),'-movflags','+faststart',str(stage/NAMES[0])],check=True)
        rupture=next(e['time'] for e in record['simulation']['events'] if e['kind']=='wall_ruptured')
        times=(0.,1.15,3.6,6.5,rupture-.20,rupture+.50)
        sheet=Image.new('RGB',(1152,1410),(7,12,23));draw=ImageDraw.Draw(sheet)
        try:font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18)
        except OSError:font=ImageFont.load_default()
        draw.text((24,16),'MS06.3D / PB-2.0 / REVIEW SPOILERS',fill=(215,233,239),font=font)
        for i,t in enumerate(times):
            x,y=24+(i%3)*372,64+(i//3)*668
            sheet.paste(renderer.render(t).resize((360,640),Image.Resampling.LANCZOS),(x,y))
            draw.text((x,y+643),f'{t:.3f}s',fill=(210,228,239),font=font)
        sheet.save(stage/NAMES[2])
        media={n:inspect_media(stage/n) for n in NAMES[:2]}
        if media[NAMES[0]]['video_stream_sha256']!=media[NAMES[1]]['video_stream_sha256']:raise ValueError('Encoded video streams differ')
        for m in media.values():
            v=next(s for s in m['probe']['streams'] if s['codec_type']=='video')
            if int(v['nb_frames'])!=tape.frame_count or v['codec_name']!='h264' or v['pix_fmt']!='yuv420p':raise ValueError('Bad encoded review format')
        if file_hash(output/NAMES[4])!=timeline_hash:raise ValueError('Timeline changed during render')
        freeze_sources(config_path,output)
        sim=record['simulation'];event=next(e for e in sim['events'] if e['kind']=='wall_ruptured')
        initial=sim['initial']['balls'];final=sim['final']['balls']
        manifest={'schema':'ms06.3d.review-manifest.v1','rules':'PB-2.0','constants':record['constants'],
                  'rules_sha256':record['rules_sha256'],'status':'owner-and-wife normal-speed phone review pending',
                  'provenance':'one directed capacity-based prototype, not an automatically selected candidate; explicitly nonphysical',
                  'scenario_seed':record['configuration']['seed'],'configuration':record['configuration'],
                  'configuration_sha256':record['configuration_sha256'],'simulation_sha256':record['simulation_sha256'],
                  'event_sha256':record['event_sha256'],'layout_sha256':record['layout_sha256'],
                  'layout_status':record['layout']['status'],'outcome':sim['final']['outcome'],
                  'terminal_time':sim['final']['time'],'terminal_reason':sim['final']['reason'],
                  'event_counts':report['base']['event_counts'],'event_times':report['base']['event_times'],
                  'peak_live_count':report['base']['peak_live'],'capacity_history':report['base']['capacity_history'],
                  'wall_arithmetic_at_rupture':event['payload'],'robustness':report,
                  'initial_by_lineage':dict(Counter(b['lineage'] for b in initial)),
                  'final_by_lineage':dict(Counter(b['lineage'] for b in final)),
                  'final_by_generation':dict(Counter(str(b['generation']) for b in final)),
                  'resistance_distribution':{'minimum':min(b['resistance'] for b in initial),'maximum':max(b['resistance'] for b in initial),'initial':{b['id']:b['resistance'] for b in initial}},
                  'audio':audio,'presentation':record['presentation'],'media':media,'contact_sheet_times':times,
                  'frame_sha256':{str(t):hashlib.sha256(renderer.render(t).tobytes()).hexdigest() for t in times},
                  'freeze':record['freeze']}
        names=(*NAMES[:6],'ms06.3d-conformance-v1.json')
        manifest['files']={n:{'sha256':file_hash((stage if n in NAMES[:4] else output)/n),
                              'bytes':((stage if n in NAMES[:4] else output)/n).stat().st_size} for n in names}
        (stage/NAMES[6]).write_text(json.dumps(manifest,indent=2)+'\n')
        for n in (*NAMES[:4],NAMES[6]):(stage/n).replace(output/n)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/ms06.3d.json')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'outputs/ms06.3d')
    args=parser.parse_args();m=render_frozen(args.config,args.output_dir)
    print(f"MS06.3D: {m['outcome']}; {m['presentation']['duration']:.3f}s; phone review pending")
