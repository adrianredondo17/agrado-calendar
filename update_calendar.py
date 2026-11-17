"""Todoturf race-card importer (phase 1). Never guesses race results."""
import json, os, re, sys, time, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

BASE = 'https://www.todoturf.net/'
STALLIONS = ('BOW CREEK', 'NOOZHOH CANARIAS', 'RODABALLO', 'NARANCO')
DATA = Path('calendar.json')
HEADERS = {'User-Agent': 'AgradoCalendar/0.1 (public racing data; low-frequency checks)'}
S = requests.Session(); S.headers.update(HEADERS)

def norm(s):
    s = unicodedata.normalize('NFKD', str(s).upper())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]+', ' ', s).strip()

def get(url):
    if urlparse(url).netloc not in ('www.todoturf.net', 'todoturf.net'):
        raise ValueError('Unexpected domain: '+url)
    r = S.get(url, timeout=25); r.raise_for_status(); time.sleep(.4)
    return BeautifulSoup(r.content, 'html.parser')

def links(soup, filename):
    return [urljoin(BASE,a['href']) for a in soup.select('a[href]') if filename in a['href']]

def unique(seq): return list(dict.fromkeys(seq))

def parse_date(url):
    value = parse_qs(urlparse(url).query).get('fecha', [''])[0]
    return value[:10]

def horse_names(sire):
    from urllib.parse import urlencode
    url = BASE + 'productossemental2.php?' + urlencode({'nombresemental': sire})
    soup = get(url)
    table = next((t for t in soup.select('table') if 'Madre' in t.get_text(' ', strip=True) and 'Ganancias' in t.get_text(' ', strip=True)), None)
    if table is None: raise ValueError('Products table not found for '+sire)
    names = set()
    for tr in table.select('tr'):
        cells = tr.find_all('td')
        if not cells: continue
        a = cells[0].find('a')
        if not a: continue
        name = a.get_text(' ', strip=True)
        name = re.sub(r'\s+(?:Cas\.|C\.|Y\.|M\.).*$', '', name, flags=re.I)
        name = re.sub(r'\s*\((?:FR|GB|IRE|USA|ITY|GER|SPA|POR)\)\s*$', '', name, flags=re.I)
        name = re.sub(r'\s*,\s*20\d\d$', '', name)
        if name: names.add(norm(name))
    if not names: raise ValueError('No products found for '+sire)
    return names

def race_data(url):
    soup = get(url)
    title = soup.find(['h1','h2','h3'], string=re.compile(r'Premio',re.I))
    if not title:
        title = next((x for x in soup.find_all(['h1','h2','h3']) if 'Premio ' in x.get_text(' ',strip=True)),None)
    if not title: return []
    heading = title.get_text(' ',strip=True)
    match = re.search(r'carrera.*?(\d\d/\d\d/\d{4}).*?hip[oó]dromo de\s+(.+)', soup.get_text(' ',strip=True), re.I)
    if not match: return []
    day, venue = match.groups()
    iso = datetime.strptime(day,'%d/%m/%Y').strftime('%Y-%m-%d')
    if iso < datetime.now(timezone.utc).date().isoformat(): return []
    table = next((t for t in soup.select('table') if 'Caballo' in t.get_text(' ',strip=True) and 'Jinete' in t.get_text(' ',strip=True)),None)
    if table is None: return []
    out=[]
    for tr in table.select('tr'):
        cells=tr.find_all('td')
        if len(cells)<4: continue
        horse_a=cells[1].find('a')
        if not horse_a: continue
        horse=horse_a.get_text(' ',strip=True)
        horse=re.sub(r'\s*\((?:FR|GB|IRE|USA|ITY|GER|SPA|POR)\).*$', '', horse, flags=re.I).strip()
        number=cells[0].get_text(' ',strip=True)
        jockey=cells[3].get_text(' ',strip=True)
        # A published programme can be provisional. Require real number and jockey.
        if not number.isdigit() or int(number)==0 or not jockey: continue
        out.append({'date':iso,'horse':horse,'prize':heading,'venue':venue,'raceUrl':url,
                    'status':'participant','source':'todoturf','jockey':jockey,'number':number})
    return out

def main():
    if not DATA.exists(): raise RuntimeError('calendar.json missing')
    original=json.loads(DATA.read_text(encoding='utf-8'))
    existing=original.get('participants',[])
    # Fail closed: any source parsing problem means no update at all.
    sires={s:horse_names(s) for s in STALLIONS}
    program=get(BASE+'programa.php')
    meetings=unique(links(program,'programa2.php'))
    if not meetings: raise RuntimeError('No meeting links found: site structure may have changed')
    race_urls=[]
    for meeting in meetings:
        race_urls.extend(links(get(meeting),'programa3.php'))
    race_urls=unique(race_urls)
    if not race_urls: raise RuntimeError('No race links found: site structure may have changed')
    found=[]
    for url in race_urls:
        for entry in race_data(url):
            for sire,names in sires.items():
                if norm(entry['horse']) in names:
                    found.append({**entry,'sire':sire,'id':entry['date']+'|'+norm(entry['horse'])+'|'+urlparse(url).query})
                    break
    # Preserve already listed participants when a meeting vanishes from the future programme.
    # No automatic removals until official result verification has been implemented.
    by_id={x['id']:x for x in existing if isinstance(x,dict) and 'id' in x}
    for item in found: by_id[item['id']]=item
    original['participants']=sorted(by_id.values(),key=lambda x:(x.get('date',''),x.get('horse','')))
    original['stallions']=list(STALLIONS)
    original['lastUpdated']=datetime.now(timezone.utc).isoformat()
    DATA.write_text(json.dumps(original,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Checked {len(meetings)} meetings, {len(race_urls)} races; found {len(found)} qualifying entries; total {len(original["participants"])} participants')
    print('Results and videos are NOT imported by this phase.')

if __name__=='__main__':
    try: main()
    except Exception as e:
        print(f'SAFE FAILURE: {e}',file=sys.stderr)
        sys.exit(1)
