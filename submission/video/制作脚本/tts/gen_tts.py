import json, subprocess, sys, asyncio
import edge_tts
FF=r'D:\app\ffmpeg-2025-05-05-git-f4e72eb5a3-full_build\bin'
cfg=json.load(open('narration.json',encoding='utf-8'))
only=set(sys.argv[1:])
async def one(seg):
    comm=edge_tts.Communicate(seg['text'], cfg['voice'], rate=cfg['rate'], boundary='SentenceBoundary')
    subs=[]
    with open(f"{seg['id']}.mp3",'wb') as f:
        async for ch in comm.stream():
            if ch['type']=='audio': f.write(ch['data'])
            elif ch['type'] in ('WordBoundary','SentenceBoundary'):
                subs.append({'t':ch['offset']/1e7,'d':ch['duration']/1e7,'text':ch['text']})
    json.dump(subs, open(f"{seg['id']}.subs.json",'w',encoding='utf-8'), ensure_ascii=False)
    d=subprocess.run([FF+r'\ffprobe.exe','-v','error','-show_entries','format=duration','-of','csv=p=0',f"{seg['id']}.mp3"],capture_output=True,text=True).stdout.strip()
    return seg['id'], float(d), len(subs)
async def main():
    for seg in cfg['segments']:
        if only and seg['id'] not in only: continue
        for attempt in range(3):
            try:
                print(*(await one(seg))); break
            except Exception as e:
                print('retry', seg['id'], e)
asyncio.run(main())
