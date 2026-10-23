"""Spojení skutečných dat ČSÚ, bez sčítání územních a rezidenčních součtů."""
from pathlib import Path
import pandas as pd

SOURCES = {
    'KRI05': 'https://data.csu.gov.cz/opendata/sady/KRI05/distribuce/csv',
    'CRU02M': 'https://data.csu.gov.cz/opendata/sady/CRU02M/distribuce/csv',
}
CATALOG = {
    'Nehody v silniční dopravě': 'https://data.gov.cz/datová-sada?iri=https://data.gov.cz/zdroj/datové-sady/00025593/f40915f844c6fd08ef62b0550119718c',
    'Návštěvnost hromadných ubytovacích zařízení': 'https://data.gov.cz/datová-sada?iri=https://data.gov.cz/zdroj/datové-sady/00025593/a343c97c19bfae9bc943d0b28a089599',
}

def numeric(series):
    # Chybějící a nezveřejněné hodnoty zůstávají NaN, nikdy se nemění na nulu.
    return pd.to_numeric(series.str.replace('\u00a0', '', regex=False)
                         .str.replace(' ', '', regex=False)
                         .str.replace(',', '.', regex=False), errors='coerce')

def load_and_merge(folder):
    folder = Path(folder)
    a = pd.read_csv(folder / 'KRI05.csv', dtype=str, encoding='utf-8-sig')
    t = pd.read_csv(folder / 'CRU02M.csv', dtype=str, encoding='utf-8-sig')
    # Krajské součty mají vyplněný kraj, ale prázdný okres.
    a = a[a['Uz023h.KRAJ'].str.fullmatch(r'CZ\d{3}', na=False)
          & a['Uz023h.OKRES'].fillna('').eq('')
          & a['IndicatorType'].eq('6073N')].copy()
    a = a.rename(columns={'Uz023h.KRAJ': 'kod_kraje', 'CasR': 'rok',
                           'Česko, kraje, okresy-Kraj': 'kraj'})
    a['nehody'] = numeric(a['Hodnota'])
    a['rok'] = pd.to_numeric(a['rok'], errors='raise').astype(int)
    a = a[['kod_kraje', 'kraj', 'rok', 'nehody']]
    if a.duplicated(['kod_kraje', 'rok']).any():
        raise ValueError('Nehody obsahují duplicitní kraj a rok. Ověř strukturu zdroje.')
    # ČSÚ používá v různých verzích exportu dvě pojmenování území.
    geo = 'Uz02' if 'Uz02' in t.columns else 'Uz02.KRAJ'
    t = t[t[geo].str.fullmatch(r'CZ\d{3}', na=False)
          & t['REZIDENCE'].eq('0') & t['KATHUZ'].eq('1')
          & t['Ukazatel'].str.strip().isin(['Počet hostů', 'Počet přenocování'])].copy()
    t = t.rename(columns={geo: 'kod_kraje'})
    t['hodnota'] = numeric(t['Hodnota'])
    t['datum'] = pd.to_datetime(t['CasM'], format='%Y-%m', errors='raise')
    t['rok'] = t['datum'].dt.year
    t['ukazatel'] = t['Ukazatel'].str.strip().map(
        {'Počet hostů': 'hoste', 'Počet přenocování': 'prenocovani'})
    if t.duplicated(['kod_kraje', 'datum', 'ukazatel']).any():
        raise ValueError('Návštěvnost obsahuje duplicitní měsíc. Ověř filtry součtů.')
    g = t.groupby(['kod_kraje', 'rok', 'ukazatel'])
    annual = g.agg(hodnota=('hodnota', lambda x: x.sum(min_count=12)),
                   mesice=('datum', 'nunique'), platne=('hodnota', 'count')).reset_index()
    annual = annual[(annual['mesice'] == 12) & (annual['platne'] == 12)]
    annual = annual.pivot(index=['kod_kraje', 'rok'], columns='ukazatel',
                          values='hodnota').reset_index()
    result = a.merge(annual, on=['kod_kraje', 'rok'], how='inner', validate='one_to_one')
    result = result.dropna(subset=['hoste', 'prenocovani', 'nehody'])
    if result.empty:
        raise ValueError('Zdrojové soubory neobsahují společné úplné roky.')
    return result.sort_values(['rok', 'kraj']).reset_index(drop=True)
