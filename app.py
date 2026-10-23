"""Spuštění: python -m streamlit run app.py"""
from pathlib import Path
from datetime import datetime, timezone
import urllib.request
import pandas as pd
import plotly.express as px
import streamlit as st
from data_processing import SOURCES, CATALOG, load_and_merge

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
st.set_page_config(page_title='Turistika a nehody v ČR', layout='wide')

@st.cache_data(show_spinner=False)
def get_data(signatures):
    return load_and_merge(DATA)

def download_sources():
    DATA.mkdir(exist_ok=True)
    # Nejdříve stáhni oba soubory dočasně. Při chybě zachovej původní data.
    temporary = []
    try:
        for code, url in SOURCES.items():
            path = DATA / (code + '.download')
            temporary.append((path, DATA / (code + '.csv')))
            with urllib.request.urlopen(url, timeout=180) as response, path.open('wb') as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
            cols = pd.read_csv(path, nrows=0).columns
            if not {'Ukazatel', 'Hodnota'}.issubset(cols):
                raise ValueError('Server nevrátil očekávaný CSV soubor.')
        for path, target in temporary:
            path.replace(target)
        (DATA / 'stazeno.txt').write_text(datetime.now(timezone.utc).isoformat(), encoding='utf-8')
    finally:
        for path, _ in temporary:
            path.unlink(missing_ok=True)

st.title('Turistická návštěvnost a dopravní nehody v krajích ČR')
st.write('Dvě oblasti otevřených dat propojené přes kód kraje a rok. Zdroj: ČSÚ, katalog data.gov.cz.')
with st.sidebar:
    st.header('Data a filtry')
    refresh = st.button('Stáhnout aktuální data')
try:
    if refresh or any(not (DATA / (code + '.csv')).exists() for code in SOURCES):
        with st.spinner('Stahuji data ČSÚ. Návštěvnost má přibližně 70 MB, stažení může trvat několik minut.'):
            download_sources()
        get_data.clear()
    signatures = tuple((DATA / (code + '.csv')).stat().st_mtime_ns for code in SOURCES)
    df = get_data(signatures)
except Exception as exc:
    st.error(f'Data se nepodařilo načíst: {exc}')
    st.info('Zkontroluj připojení a soubory data/KRI05.csv a data/CRU02M.csv. Pak aplikaci obnov.')
    st.stop()

years = sorted(df['rok'].unique().tolist())
with st.sidebar:
    year = st.selectbox('Rok pro porovnání krajů', years, index=len(years)-1)
    regions = sorted(df['kraj'].unique())
    selected = st.multiselect('Kraje', regions, default=regions)
    tourist_metric = st.selectbox('Ukazatel návštěvnosti', ['hoste', 'prenocovani'],
                                 format_func=lambda x: {'hoste': 'Počet hostů', 'prenocovani': 'Počet přenocování'}[x])
    omit_praha = st.checkbox('Vynechat Prahu', value=False)
    st.caption('Používají se pouze úplné roky se 12 měsíci a zveřejněnými hodnotami.')
    stamp = DATA / 'stazeno.txt'
    if stamp.exists():
        st.caption('Stažení dat (UTC): ' + stamp.read_text(encoding='utf-8').strip())
if omit_praha:
    selected = [x for x in selected if x != 'Hlavní město Praha']
f = df[df['kraj'].isin(selected)]
current = f[f['rok'] == year]
if current.empty:
    st.info('Pro zvolený rok a kraje nejsou dostupná data. Změň filtry.')
    st.stop()
labels = {'hoste': 'Počet hostů', 'prenocovani': 'Počet přenocování',
          'nehody': 'Počet dopravních nehod', 'kraj': 'Kraj', 'rok': 'Rok'}
a, b, c = st.columns(3)
a.metric('Hosté ve vybraných krajích', f"{current['hoste'].sum():,.0f}".replace(',', ' '))
b.metric('Dopravní nehody', f"{current['nehody'].sum():,.0f}".replace(',', ' '))
c.metric('Počet krajů', len(current))
st.subheader(f'Porovnání krajů v roce {year}')
scatter = px.scatter(current, x=tourist_metric, y='nehody', color='kraj',
                     hover_name='kraj', hover_data=['rok', 'hoste', 'prenocovani', 'nehody'],
                     labels=labels)
scatter.update_traces(marker_size=13)
st.plotly_chart(scatter, width='stretch')
if len(current) >= 3 and current[tourist_metric].nunique() > 1 and current['nehody'].nunique() > 1:
    r = current[tourist_metric].corr(current['nehody'])
    st.write(f'Pearsonův korelační koeficient pro vybrané kraje v tomto roce: {r:.3f}.')
st.caption('Souvislost není důkaz příčiny. Počty ovlivňuje velikost krajů, obyvatelstvo i intenzita dopravy. Hosté jsou příjezdy do ubytovacích zařízení, nikoli počet unikátních osob. Nehody zahrnují všechny evidované nehody, nejen nehody turistů.')
st.subheader('Vývoj v čase')
st.write('Výběr roku řídí porovnání výše. Grafy níže zobrazují celé dostupné období pro vybrané kraje.')
left, right = st.columns(2)
with left:
    st.plotly_chart(px.line(f, x='rok', y=tourist_metric, color='kraj', markers=True,
                           labels=labels), width='stretch')
with right:
    st.plotly_chart(px.line(f, x='rok', y='nehody', color='kraj', markers=True,
                           labels=labels), width='stretch')
st.subheader('Spojená data')
st.dataframe(current.rename(columns=labels), hide_index=True, width='stretch')
st.download_button('Stáhnout spojená data vybraných krajů za všechny roky',
                   f.to_csv(index=False).encode('utf-8-sig'),
                   file_name='turistika_a_nehody.csv', mime='text/csv')
with st.expander('Zdroje a postup zpracování'):
    for name, url in CATALOG.items():
        st.link_button(name + ' na data.gov.cz', url)
    st.write('Nehody: krajské roční součty, bez okresních řádků. Návštěvnost: rezidence celkem a HUZ celkem, součet 12 měsíců zvlášť pro hosty a přenocování. Spojení je jedna ku jedné podle kódu kraje a roku. Chybějící hodnoty se nenahrazují nulou. Neúplné roky a neúplné dvojice kraj a rok se vynechávají.')
