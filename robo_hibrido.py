#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║   🤖  ROBO HIBRIDO  v4.2  —  SHOPEE & ALIEXPRESS FIX               ║
║   Extratores turbinados + mais URLs                                 ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import re
import logging
import random
import time
import json
import os
import sys
import hashlib
import threading
from collections import deque
from typing import List, Dict, Set, Tuple, Optional
from datetime import datetime
from pathlib import Path
from difflib import SequenceMatcher

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from tqdm import tqdm
from colorama import init, Fore, Style
init(autoreset=True)

# =============================================================================
# CONFIGURACOES
# =============================================================================

AFILIADO = {
    "mercadolivre.com.br": "matt_word=mafa20240108123433&matt_tool=27785129",
    "mercadolibre.com":    "matt_word=mafa20240108123433&matt_tool=27785129",
    "shopee.com.br":       "mmp_pid=an_18392210092&utm_source=an_18392210092&utm_campaign=id_9YYI32uJkJ&utm_medium=affiliates&utm_term=embnbh8cb1pj",
    "magazineluiza.com.br":"promoter_id=5492332&partner_id=3440",
    "amazon.com.br":       "tag=influencer-031e550d-20",
    "amazon.com":          "tag=influencer-031e550d-20",
    "aliexpress.com":      "aff_platform=portals-promotion&sk=_mOsSJgZ&aff_trace_key=&terminal_id=&afSmartRedirect=y",
    "pt.aliexpress.com":   "aff_platform=portals-promotion&sk=_mOsSJgZ&aff_trace_key=&terminal_id=&afSmartRedirect=y",
    "kabum.com.br":        "awc=27262_1234567890&utm_source=afiliado",
    "pichau.com.br":       "gref=afiliado&parceiro=promobot",
    "terabyteshop.com.br": "afiliado=promobot",
}

TELEGRAM_TOKEN   = "8725096447:AAG7jI2vI5cU0bgYkS24vCuS27IySj65lbs"
TELEGRAM_CHAT_ID = "-1003177888647"
TELEGRAM_URL     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

DELAY_POSTS      = 15    # s entre posts no Telegram
DELAY_PLAYWRIGHT = 8     # s entre URLs
DELAY_CICLO      = 300   # s entre ciclos (5 minutos)
MAX_POSTS_CICLO  = 12    # posts maximos por ciclo
TIMEOUT_PAGE     = 25000 # ms

DESC_MIN = {"HARDWARE": 10, "ELETRONICO": 20, "GERAL": 35}

ARQ_ENVIADOS  = "data/enviados.json"
ARQ_HISTORICO = "data/historico.json"

Path("data").mkdir(exist_ok=True)
Path("logs").mkdir(exist_ok=True)

# =============================================================================
# LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("Bot")

# =============================================================================
# ESTADO GLOBAL THREAD-SAFE
# =============================================================================

_lock      = threading.Lock()
_enviados: Set[str]   = set()
_historico: deque     = deque(maxlen=80)
_sessao    = {"HARDWARE": 0, "ELETRONICO": 0, "GERAL": 0, "total": 0}
_modo_teste = False

# =============================================================================
# CLASSIFICADOR
# =============================================================================

KW_IGNORAR = [
    "capinha","case celular","pelicula","cabo usb","carregador generico",
    "adaptador micro","suporte de parede","vassoura","rodo","pano microfibra",
    "sabao","desengordurante","capa de celular","cabo hdmi",
]

KW_HARDWARE = [
    "rtx 3","rtx 4","gtx 16","gtx 10","rx 6","rx 7","rx 9","radeon","geforce",
    "placa de video","placa de vídeo","placa grafica","gpu",
    "processador","ryzen","intel core i","core ultra","threadripper","athlon","cpu",
    "memoria ram","memória ram","ddr4","ddr5","dimm","sodimm",
    "ssd","nvme","m.2","hd sata","disco rigido","disco rígido","hdd",
    "placa mae","placa mãe","motherboard",
    "fonte atx","fonte modular","psu","80 plus",
    "water cooler","cooler cpu","cooler processador","dissipador","pasta termica",
    "gabinete gamer","gabinete mid","gabinete full",
    "teclado gamer","teclado mecanico","mouse gamer","headset gamer",
    "mousepad gamer","cadeira gamer","monitor gamer","monitor 144hz",
    "notebook gamer","pc gamer","computador gamer",
]

KW_ELETRONICO = [
    "smart tv","smarttv","tv 4k","tv oled","tv qled","tv led","televisão",
    "monitor 4k","headset","fone de ouvido","fone bluetooth","earphone","earbuds",
    "airpods","soundbar","caixa de som","smartphone","iphone","galaxy s","galaxy a",
    "galaxy z","redmi","poco","moto g","tablet","smartwatch","relógio inteligente",
    "projetor","drone","camera digital","webcam","console","playstation","xbox",
]

MARCAS = [
    "nike","adidas","samsung","lg","sony","philips","brastemp","consul",
    "electrolux","bosch","makita","dewalt","stanley","multilaser","mondial",
    "arno","britania","oster","black decker","tramontina","positivo","xiaomi",
    "jbl","apple","motorola","lenovo","dell","hp","acer","asus","gigabyte",
    "msi","evga","corsair","kingston","hyperx","wd","seagate","logitech",
    "razer","redragon","pichau","kabum","terabyte","mancer","superframe",
]

def categoria(nome: str) -> str:
    n = nome.lower()
    for kw in KW_IGNORAR:
        if kw in n: return "IGNORAR"
    for kw in KW_HARDWARE:
        if kw in n: return "HARDWARE"
    for kw in KW_ELETRONICO:
        if kw in n: return "ELETRONICO"
    return "GERAL"

SUBCAT_MAP = {
    "gpu":      ["rtx","gtx","rx","radeon","geforce","placa de video"],
    "cpu":      ["processador","ryzen","intel core","threadripper"],
    "ram":      ["ram","ddr4","ddr5","memoria"],
    "ssd":      ["ssd","nvme","m.2","hd sata"],
    "fonte":    ["fonte atx","fonte modular","psu"],
    "gabinete": ["gabinete gamer","gabinete mid"],
    "cooler":   ["cooler","water cooler","dissipador"],
    "monitor":  ["monitor gamer","monitor 144hz","monitor 240hz"],
    "notebook": ["notebook gamer"],
    "periferico":["teclado gamer","mouse gamer","headset gamer"],
}

def subcategoria(nome: str) -> str:
    n = nome.lower()
    for sub, kws in SUBCAT_MAP.items():
        if any(k in n for k in kws): return sub
    return "outro"

# =============================================================================
# SCORE E FILTROS
# =============================================================================

SCORE_BASE = {"HARDWARE": 100, "ELETRONICO": 60, "GERAL": 20, "IGNORAR": 0}

def calcular_score(p: Dict) -> float:
    cat  = p.get("categoria","GERAL")
    desc = p.get("desconto",0)
    econ = p.get("economia",0)
    prec = p.get("preco_desconto",0)
    s = SCORE_BASE.get(cat,20) + desc*2 + econ/100
    if prec >= 1500 and desc >= 20: s += 40
    elif prec >= 800 and desc >= 15: s += 20
    elif prec >= 400 and desc >= 12: s += 10
    if any(m in p.get("nome","").lower() for m in MARCAS): s += 8
    return round(s, 2)

def filtrar(p: Dict) -> Tuple[bool, str]:
    cat  = p.get("categoria","GERAL")
    desc = p.get("desconto",0)
    econ = p.get("economia",0)
    prec = p.get("preco_desconto",0)
    nome = p.get("nome","")

    if cat == "IGNORAR":
        return False, "spam"
    if desc <= 0:
        return False, "sem desconto"
    if cat == "HARDWARE":
        return (desc >= DESC_MIN["HARDWARE"], f"HW {desc:.0f}%")
    if cat == "ELETRONICO":
        return (desc >= DESC_MIN["ELETRONICO"], f"EL {desc:.0f}%")
    if cat == "GERAL":
        if prec < 35:
            return False, f"preco baixo R${prec:.0f}"
        if desc >= DESC_MIN["GERAL"] or econ >= 120:
            if any(m in nome.lower() for m in MARCAS) or desc >= 50:
                return True, f"GE {desc:.0f}%"
        return False, f"GE {desc:.0f}% sem criterio"
    return False, "?"

# =============================================================================
# ANTI-SPAM E PROPORÇÃO
# =============================================================================

def antispam_ok(p: Dict) -> bool:
    nome  = p["nome"]
    cat   = p["categoria"]
    sub   = p.get("subcategoria","outro")
    hist  = list(_historico)
    for h in hist[-12:]:
        if SequenceMatcher(None, nome.lower(), h["nome"].lower()).ratio() > 0.75:
            return False
    if cat == "HARDWARE" and sub != "outro":
        if [h.get("subcategoria") for h in hist[-3:]].count(sub) >= 3:
            return False
    if [h.get("categoria") for h in hist[-4:]].count(cat) >= 4:
        return False
    return True

PROP = {"HARDWARE": 0.70, "ELETRONICO": 0.20, "GERAL": 0.10}

def proporcao_ok(cat: str) -> bool:
    total = _sessao["total"]
    if total < 3: return True
    return (_sessao.get(cat,0) / total) <= PROP.get(cat,0.10) * 1.25

def ciclo_cheio() -> bool:
    with _lock: return _sessao["total"] >= MAX_POSTS_CICLO

# =============================================================================
# UTILIDADES
# =============================================================================

def fmt_preco(v: float) -> str:
    if v <= 0: return "R$ --"
    if v >= 1000:
        r = int(v); c = int(round((v-r)*100))
        return "R$ " + f"{r:,}".replace(",",".") + f",{c:02d}"
    return f"R$ {v:.2f}".replace(".",",")

def parse_preco(txt) -> float:
    if txt is None: return 0.0
    s = re.sub(r"[^\d,.]","", str(txt).strip())
    if not s: return 0.0
    if "," in s and "." in s:
        s = s.replace(".","").replace(",",".") if s.rfind(",") > s.rfind(".") else s.replace(",","")
    elif "," in s:
        s = s.replace(",",".")
    try: return float(s)
    except: return 0.0

def calc_desconto(preco: float, orig: float) -> Tuple[float, float]:
    if orig > preco > 0:
        return round((orig-preco)/orig*100, 2), round(orig-preco, 2)
    return 0.0, 0.0

def aplicar_afiliado(url: str) -> str:
    for dom, par in AFILIADO.items():
        if dom in url and par:
            sep = "&" if "?" in url else "?"
            return url + sep + par
    return url

def hid(link: str) -> str:
    return hashlib.md5(link.encode()).hexdigest()[:16]

# =============================================================================
# PERSISTENCIA
# =============================================================================

def load_enviados() -> Set[str]:
    try:
        with open(ARQ_ENVIADOS) as f: return set(json.load(f))
    except: return set()

def save_enviados():
    try:
        with open(ARQ_ENVIADOS,"w") as f:
            json.dump(list(_enviados)[-3000:], f)
    except: pass

def load_historico() -> list:
    try:
        with open(ARQ_HISTORICO, encoding="utf-8") as f: return json.load(f)
    except: return []

def save_historico():
    try:
        with open(ARQ_HISTORICO,"w",encoding="utf-8") as f:
            json.dump(list(_historico), f, ensure_ascii=False)
    except: pass

# =============================================================================
# MENSAGEM
# =============================================================================

GATILHOS = {
    55:"🔥🔥 ABSURDO! PREÇO HISTÓRICO!",
    40:"🔥 PROMOÇÃO IMPERDÍVEL!",
    30:"⚡ OFERTA ESPECIAL!",
    20:"💰 DESCONTO INCRÍVEL!",
    10:"🎯 BOA OFERTA!",
     0:"💡 OFERTA DO DIA",
}
CTA_HW  = ["🚀 Roda tudo no ultra! Upgrade agora.",
           "⚡ Performance máxima com desconto real.",
           "🎮 Hora de dar aquele upgrade no setup!",
           "💻 Hardware top pelo menor preço.",
           "🔧 Monte seu PC Gamer gastando menos!"]
CTA_OUT = ["💸 Preço absurdo — não volta mais.",
           "⏰ Corre antes de acabar o estoque!",
           "🤑 Uma das melhores oportunidades do mês.",
           "📦 Entrega rápida + desconto real.",
           "🛒 Manda pros amigos!"]
ICON_SUB = {"gpu":"🎮","cpu":"⚡","ram":"🧠","ssd":"💾","gabinete":"🖥️",
            "fonte":"🔌","cooler":"❄️","monitor":"🖥️","notebook":"💻",
            "periferico":"🕹️","outro":"🔧"}

def montar_mensagem(p: Dict) -> str:
    cat  = p.get("categoria","GERAL")
    sub  = p.get("subcategoria","outro")
    desc = p.get("desconto",0)
    nome = p.get("nome","")[:150]
    econ = p.get("economia",0)
    orig = p.get("preco_original",0)
    prec = p.get("preco_desconto",0)
    link = p.get("link","")
    plat = p.get("plataforma","")
    icon = p.get("plataforma_icone","🛒")

    gtl = next((t for lim,t in sorted(GATILHOS.items(),reverse=True) if desc>=lim), "💡 OFERTA")
    linhas = [gtl]
    if cat == "HARDWARE":
        linhas.append(f"{ICON_SUB.get(sub,'🔧')} <b>{sub.upper()} — PC GAMER</b>")
        cta = random.choice(CTA_HW)
    elif cat == "ELETRONICO":
        linhas.append("📱 <b>ELETRÔNICO EM OFERTA</b>")
        cta = random.choice(CTA_OUT)
    else:
        linhas.append("🏷️ <b>OFERTA VIRAL</b>")
        cta = random.choice(CTA_OUT)
    linhas += [
        f"{icon} <b>{plat}</b>",
        f"🔥 <b>{nome}</b>",
        f"💰 <s>De: {fmt_preco(orig)}</s>\n💵 <b>Por: {fmt_preco(prec)}</b>\n💸 Economia: {fmt_preco(econ)} | 🎯 {desc:.0f}% OFF",
        cta,
        f"🛒 <a href='{link}'><b>👉 COMPRAR AGORA 👈</b></a>",
    ]
    return "\n\n".join(linhas)

# =============================================================================
# TELEGRAM
# =============================================================================

def enviar_telegram(p: Dict) -> bool:
    msg = montar_mensagem(p)
    if p.get("imagem"):
        try:
            r = requests.post(f"{TELEGRAM_URL}/sendPhoto",
                json={"chat_id":TELEGRAM_CHAT_ID,"photo":p["imagem"],"caption":msg,"parse_mode":"HTML"},
                timeout=20)
            if r.status_code == 200: return True
        except: pass
    try:
        r = requests.post(f"{TELEGRAM_URL}/sendMessage",
            json={"chat_id":TELEGRAM_CHAT_ID,"text":msg,"parse_mode":"HTML"},
            timeout=20)
        return r.status_code == 200
    except Exception as e:
        log.error(f"Telegram: {e}")
        return False

# =============================================================================
# PIPELINE THREAD-SAFE
# =============================================================================

def enriquecer(p: Dict) -> Dict:
    p["categoria"]    = categoria(p["nome"])
    p["subcategoria"] = subcategoria(p["nome"])
    p["score"]        = calcular_score(p)
    return p

def processar(p: Dict) -> bool:
    p = enriquecer(p)
    ok, mot = filtrar(p)
    if not ok:
        log.debug(f"  ✗ {p['nome'][:50]} [{mot}]")
        return False

    with _lock:
        if p["id"] in _enviados:             return False
        if not antispam_ok(p):               return False
        if not proporcao_ok(p["categoria"]): return False
        if _sessao["total"] >= MAX_POSTS_CICLO: return False
        _enviados.add(p["id"])
        _sessao["total"] += 1
        _sessao[p["categoria"]] = _sessao.get(p["categoria"],0) + 1

    cat  = p["categoria"]; sub = p.get("subcategoria","outro")
    desc = p["desconto"];  sc  = p["score"]
    nome = p["nome"][:55]; plat = p["plataforma"]

    if _modo_teste:
        log.info(Fore.YELLOW + f"  🧪 [{cat}][{sub}] {desc:.0f}% score={sc:.0f} | {plat} | {nome}" + Style.RESET_ALL)
        with _lock:
            _historico.append({"id":p["id"],"nome":p["nome"],"categoria":cat,"subcategoria":sub})
            save_historico(); save_enviados()
        return True

    ok_env = enviar_telegram(p)
    if ok_env:
        with _lock:
            _historico.append({"id":p["id"],"nome":p["nome"],"categoria":cat,
                               "subcategoria":sub,"ts":datetime.now().isoformat()})
            save_historico(); save_enviados()
        log.info(Fore.GREEN + f"  ✅ [{cat}] {desc:.0f}% OFF score={sc:.0f} | {nome}" + Style.RESET_ALL)
        time.sleep(DELAY_POSTS)
    else:
        with _lock:
            _enviados.discard(p["id"])
            _sessao["total"] = max(0, _sessao["total"]-1)
            _sessao[cat] = max(0, _sessao.get(cat,1)-1)
    return ok_env

# =============================================================================
# FUNÇÕES DE SCROLL
# =============================================================================

def _scroll_page(page, vezes=3):
    """Rola a página para carregar mais produtos."""
    for i in range(vezes):
        try:
            page.evaluate("window.scrollBy(0, window.innerHeight)")
            page.wait_for_timeout(1000)
        except: pass
    try:
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)
    except: pass

# =============================================================================
# EXTRATORES PLAYWRIGHT
# =============================================================================

# -----------------------------------------------------------------------------
# MERCADO LIVRE
# -----------------------------------------------------------------------------
def extrair_mercadolivre(html: str) -> List[Dict]:
    """Extrator Mercado Livre via HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    produtos = []
    
    cards = (soup.select('li.ui-search-layout__item') or
             soup.select('.ui-search-result__content') or
             soup.select('.poly-card__content') or
             soup.select('[data-testid="result-card"]'))
    
    if not cards:
        cards = soup.find_all('div', class_=re.compile(r'result|item|product'))
    
    for card in cards[:25]:
        try:
            # Nome
            nome = None
            for sel in ['.ui-search-item__title', '.poly-component__title', 
                        'h2', '[data-testid="product-title"]']:
                elem = card.select_one(sel)
                if elem:
                    nome = elem.get_text(strip=True)
                    break
            if not nome or len(nome) < 5: continue
            
            # Preço
            preco = 0
            for sel in ['.andes-money-amount__fraction', '.price-tag-amount',
                        '[data-testid="price"]']:
                elem = card.select_one(sel)
                if elem:
                    preco = parse_preco(elem.get_text())
                    if preco > 0: break
            if preco <= 0: continue
            
            # Preço original
            preco_original = preco * 1.2
            orig_elem = card.select_one('.andes-money-amount--previous .andes-money-amount__fraction')
            if orig_elem:
                preco_original = parse_preco(orig_elem.get_text())
            
            # Badge de desconto
            badge = card.select_one('.ui-search-price__discount') or card.select_one('[class*="discount"]')
            if badge and preco_original <= preco:
                match = re.search(r'(\d+)%', badge.get_text())
                if match:
                    pct = int(match.group(1))
                    if 1 <= pct <= 90:
                        preco_original = round(preco / (1 - pct/100), 2)
            
            desc, econ = calc_desconto(preco, preco_original)
            
            # Link
            link_elem = card.select_one('a[href]') or card.find('a', href=True)
            if not link_elem: continue
            link = link_elem['href']
            if link.startswith('/'):
                link = 'https://www.mercadolivre.com.br' + link
            link = aplicar_afiliado(link)
            
            # Imagem
            img = None
            img_elem = card.select_one('img')
            if img_elem:
                for attr in ['src', 'data-src']:
                    if img_elem.get(attr):
                        img = img_elem[attr]
                        if img.startswith('http'):
                            break
            
            produtos.append({
                'id': hid(link),
                'plataforma': 'MERCADO LIVRE',
                'plataforma_icone': '🟡',
                'nome': nome,
                'preco_original': round(preco_original, 2),
                'preco_desconto': round(preco, 2),
                'desconto': desc,
                'economia': econ,
                'link': link,
                'imagem': img,
            })
        except: continue
    
    return produtos

# -----------------------------------------------------------------------------
# SHOPEE - EXTRATOR CORRIGIDO
# -----------------------------------------------------------------------------
def extrair_shopee(html: str) -> List[Dict]:
    """Extrator Shopee turbinado."""
    soup = BeautifulSoup(html, 'html.parser')
    produtos = []
    
    # Múltiplos seletores para cards
    cards = (soup.select('[data-sqe="item"]') or
             soup.select('.shopee-search-item-result__item') or
             soup.select('[class*="product-item"]') or
             soup.select('div[class*="card"]') or
             soup.find_all('li', class_=re.compile(r'item')) or
             soup.select('a[href*="product"]'))
    
    if not cards:
        # Fallback: qualquer div com link de produto
        cards = soup.find_all('div', attrs={'data-sqe': True}) or soup.find_all('div', class_=re.compile(r'product|item'))
    
    log.info(f"   🃏 Shopee: {len(cards)} cards encontrados")
    
    for card in cards[:25]:
        try:
            # TENTATIVA 1: Nome pelo data-sqe
            nome = None
            nome_elem = card.select_one('[data-sqe="name"]') or card.select_one('div[class*="name"]')
            if nome_elem:
                nome = nome_elem.get_text(strip=True)
            
            # TENTATIVA 2: Nome pelo alt da imagem
            if not nome or len(nome) < 5:
                img = card.select_one('img')
                if img and img.get('alt'):
                    nome = img['alt']
            
            # TENTATIVA 3: Qualquer texto grande
            if not nome or len(nome) < 5:
                textos = card.find_all(text=True)
                for t in textos:
                    t = t.strip()
                    if len(t) > 15 and not any(x in t.lower() for x in ['r$', 'us$', 'frete', 'vendido']):
                        nome = t
                        break
            
            if not nome or len(nome) < 5:
                continue
            
            # PREÇO
            preco = 0
            # Tenta encontrar preço em vários lugares
            for sel in ['[data-sqe="price"]', '[class*="price"]', '[class*="Price"]', 
                        'span[class*="currency"]', 'div[class*="sale-price"]']:
                precos = card.select(sel)
                for p in precos:
                    val = parse_preco(p.get_text())
                    if val > 0:
                        if val < preco or preco == 0:
                            preco = val
                if preco > 0:
                    break
            
            # Se não achou, tenta qualquer span com R$
            if preco <= 0:
                for span in card.find_all('span'):
                    txt = span.get_text()
                    if 'R$' in txt:
                        val = parse_preco(txt)
                        if val > 0:
                            preco = val
                            break
            
            if preco <= 0:
                continue
            
            # PREÇO ORIGINAL
            preco_original = preco * 1.2
            for sel in ['del', 's', '[class*="original"]', '[class*="strikethrough"]']:
                orig_elem = card.select_one(sel)
                if orig_elem:
                    val = parse_preco(orig_elem.get_text())
                    if val > preco:
                        preco_original = val
                        break
            
            # BADGE DE DESCONTO
            badge = card.select_one('[class*="discount"]') or card.select_one('[class*="percent"]') or card.select_one('[class*="badge"]')
            if badge and preco_original <= preco:
                match = re.search(r'(\d+)%', badge.get_text())
                if match:
                    pct = int(match.group(1))
                    if 1 <= pct <= 90:
                        preco_original = round(preco / (1 - pct/100), 2)
            
            desc, econ = calc_desconto(preco, preco_original)
            
            # LINK
            link = None
            link_elem = card.select_one('a[href]') or card.find('a', href=True)
            if link_elem:
                link = link_elem['href']
                if not link.startswith('http'):
                    link = 'https://shopee.com.br' + link
            
            if not link:
                continue
            
            link = aplicar_afiliado(link)
            
            # IMAGEM
            img = None
            img_elem = card.select_one('img')
            if img_elem:
                for attr in ['src', 'data-src']:
                    if img_elem.get(attr):
                        img = img_elem[attr]
                        if img.startswith('http'):
                            break
            
            produtos.append({
                'id': hid(link),
                'plataforma': 'SHOPEE',
                'plataforma_icone': '🛍️',
                'nome': nome,
                'preco_original': round(preco_original, 2),
                'preco_desconto': round(preco, 2),
                'desconto': desc,
                'economia': econ,
                'link': link,
                'imagem': img,
            })
        except Exception as e:
            log.debug(f"Shopee item error: {e}")
            continue
    
    log.info(f"   ✅ Shopee: {len(produtos)} produtos extraídos")
    return produtos

# -----------------------------------------------------------------------------
# ALIEXPRESS - EXTRATOR CORRIGIDO
# -----------------------------------------------------------------------------
def extrair_aliexpress(html: str) -> List[Dict]:
    """Extrator AliExpress turbinado."""
    soup = BeautifulSoup(html, 'html.parser')
    produtos = []
    
    # Múltiplos seletores
    cards = (soup.select('[class*="product-item"]') or
             soup.select('[class*="_2r__"]') or
             soup.select('[class*="item"]') or
             soup.select('a[href*="item"]') or
             soup.select('div[class*="card"]') or
             soup.find_all('div', class_=re.compile(r'product|item')))
    
    log.info(f"   🃏 AliExpress: {len(cards)} cards encontrados")
    
    for card in cards[:25]:
        try:
            # NOME
            nome = None
            for sel in ['[class*="title"]', '[class*="name"]', 'h3', 'a[class*="title"]']:
                elem = card.select_one(sel)
                if elem:
                    nome = elem.get_text(strip=True)
                    break
            
            if not nome or len(nome) < 5:
                img = card.select_one('img')
                if img and img.get('alt'):
                    nome = img['alt']
            
            if not nome or len(nome) < 5:
                continue
            
            # PREÇO
            preco = 0
            # Procura por preços em reais (R$)
            for elem in card.find_all(['span', 'div'], text=re.compile(r'R\$\s*\d')):
                val = parse_preco(elem.get_text())
                if val > 0:
                    if val < preco or preco == 0:
                        preco = val
            
            # Se não achou, tenta seletores específicos
            if preco <= 0:
                for sel in ['[class*="price"]', '[class*="Price"]', '[class*="current-price"]']:
                    precos = card.select(sel)
                    for p in precos:
                        val = parse_preco(p.get_text())
                        if val > 0:
                            if val < preco or preco == 0:
                                preco = val
            
            if preco <= 0:
                continue
            
            # PREÇO ORIGINAL
            preco_original = preco * 1.2
            for sel in ['del', 's', '[class*="original"]']:
                orig_elem = card.select_one(sel)
                if orig_elem:
                    val = parse_preco(orig_elem.get_text())
                    if val > preco:
                        preco_original = val
                        break
            
            # BADGE
            badge = card.select_one('[class*="discount"]') or card.select_one('[class*="off"]')
            if badge and preco_original <= preco:
                match = re.search(r'(\d+)%', badge.get_text())
                if match:
                    pct = int(match.group(1))
                    if 1 <= pct <= 90:
                        preco_original = round(preco / (1 - pct/100), 2)
            
            desc, econ = calc_desconto(preco, preco_original)
            
            # LINK
            link = None
            link_elem = card.select_one('a[href]') or card.find('a', href=True)
            if link_elem:
                link = link_elem['href']
                if not link.startswith('http'):
                    if 'aliexpress' in link:
                        link = 'https:' + link if link.startswith('//') else 'https://pt.aliexpress.com' + link
                    else:
                        link = 'https://pt.aliexpress.com' + link
            
            if not link:
                continue
            
            link = aplicar_afiliado(link)
            
            # IMAGEM
            img = None
            img_elem = card.select_one('img')
            if img_elem:
                for attr in ['src', 'data-src']:
                    if img_elem.get(attr):
                        img = img_elem[attr]
                        if img.startswith('http'):
                            break
            
            produtos.append({
                'id': hid(link),
                'plataforma': 'ALIEXPRESS',
                'plataforma_icone': '🌍',
                'nome': nome,
                'preco_original': round(preco_original, 2),
                'preco_desconto': round(preco, 2),
                'desconto': desc,
                'economia': econ,
                'link': link,
                'imagem': img,
            })
        except Exception as e:
            log.debug(f"AliExpress item error: {e}")
            continue
    
    log.info(f"   ✅ AliExpress: {len(produtos)} produtos extraídos")
    return produtos

# -----------------------------------------------------------------------------
# AMAZON
# -----------------------------------------------------------------------------
def extrair_amazon(html: str) -> List[Dict]:
    """Extrator Amazon."""
    soup = BeautifulSoup(html, 'html.parser')
    produtos = []
    
    cards = (soup.select('[data-component-type="s-search-result"]') or
             soup.select('[data-asin]') or
             soup.select('.s-result-item'))
    
    for card in cards[:20]:
        try:
            # Nome
            nome_elem = (card.select_one('h2 a span') or
                        card.select_one('.a-text-normal') or
                        card.select_one('h2'))
            if not nome_elem: continue
            nome = nome_elem.get_text(strip=True)
            if len(nome) < 5: continue
            
            # Preço
            preco = 0
            preco_el = card.select_one('.a-price:not(.a-text-price) .a-offscreen')
            if preco_el:
                preco = parse_preco(preco_el.get_text())
            if preco <= 0:
                whole = card.select_one('.a-price-whole')
                if whole:
                    w = re.sub(r'[.,]$', '', whole.get_text(strip=True).replace('.','').replace(',',''))
                    frac = card.select_one('.a-price-fraction')
                    f = frac.get_text(strip=True).zfill(2) if frac else '00'
                    try: preco = float(f"{w}.{f}")
                    except: pass
            if preco <= 0: continue
            
            # Preço original
            preco_original = preco * 1.2
            orig_el = card.select_one('.a-price.a-text-price .a-offscreen')
            if orig_el:
                orig_val = parse_preco(orig_el.get_text())
                if orig_val > preco:
                    preco_original = orig_val
            
            # Badge %
            badge = card.select_one('.a-badge-text') or card.select_one('[class*="saving"]')
            if badge and preco_original <= preco:
                match = re.search(r'(\d+)%', badge.get_text())
                if match:
                    pct = int(match.group(1))
                    if 1 <= pct <= 90:
                        preco_original = round(preco / (1 - pct/100), 2)
            
            desc, econ = calc_desconto(preco, preco_original)
            
            # Link
            link_el = card.select_one('h2 a') or card.select_one('a[href*="/dp/"]')
            if not link_el or not link_el.get('href'): continue
            link = link_el['href']
            if link.startswith('/'):
                link = 'https://www.amazon.com.br' + link
            link = aplicar_afiliado(link)
            
            # Imagem
            img = None
            img_el = card.select_one('img.s-image')
            if img_el:
                img = img_el.get('src')
            
            produtos.append({
                'id': hid(link),
                'plataforma': 'AMAZON',
                'plataforma_icone': '🟠',
                'nome': nome,
                'preco_original': round(preco_original, 2),
                'preco_desconto': round(preco, 2),
                'desconto': desc,
                'economia': econ,
                'link': link,
                'imagem': img,
            })
        except: continue
    
    return produtos

# -----------------------------------------------------------------------------
# MAGALU
# -----------------------------------------------------------------------------
def extrair_magalu(html: str) -> List[Dict]:
    """Extrator Magalu."""
    soup = BeautifulSoup(html, 'html.parser')
    produtos = []
    
    # Tenta JSON primeiro
    json_data = None
    script = soup.find('script', id='__NEXT_DATA__')
    if script:
        try:
            data = json.loads(script.string or '{}')
            props = data.get('props', {}).get('pageProps', {})
            search = props.get('search') or props.get('initialState', {}).get('search', {})
            items = search.get('products') or search.get('results') or []
            
            for item in items[:15]:
                try:
                    nome = item.get('title') or item.get('name', '')
                    if len(nome) < 5: continue
                    
                    preco = float(item.get('price') or item.get('bestPrice') or 0)
                    if preco <= 0: continue
                    if preco > 10000: preco /= 100
                    
                    orig = float(item.get('originalPrice') or item.get('listPrice') or 0)
                    if orig > 10000: orig /= 100
                    
                    if orig <= preco:
                        badge = item.get('discount') or item.get('badge')
                        if badge and isinstance(badge, str):
                            match = re.search(r'(\d+)%', badge)
                            if match:
                                pct = int(match.group(1))
                                if 1 <= pct <= 90:
                                    orig = round(preco / (1 - pct/100), 2)
                    
                    desc, econ = calc_desconto(preco, orig)
                    
                    slug = item.get('slug') or item.get('url', '')
                    if not slug: continue
                    link = slug if slug.startswith('http') else f"https://www.magazineluiza.com.br{slug if slug.startswith('/') else '/' + slug}"
                    link = aplicar_afiliado(link)
                    
                    img = item.get('thumbnail') or item.get('image', '')
                    
                    produtos.append({
                        'id': hid(link),
                        'plataforma': 'MAGALU',
                        'plataforma_icone': '🔵',
                        'nome': nome,
                        'preco_original': round(orig, 2),
                        'preco_desconto': round(preco, 2),
                        'desconto': desc,
                        'economia': econ,
                        'link': link,
                        'imagem': img,
                    })
                except: continue
        except: pass
    
    # Fallback: HTML
    if not produtos:
        cards = (soup.select('[data-testid="product-card"]') or
                soup.select('[class*="ProductCard"]') or
                soup.select('article'))
        
        for card in cards[:15]:
            try:
                nome_el = (card.select_one('[data-testid="product-title"]') or
                          card.select_one('h2'))
                if not nome_el: continue
                nome = nome_el.get_text(strip=True)
                
                preco_el = (card.select_one('[data-testid="price-value"]') or
                           card.select_one('[class*="price"]'))
                if not preco_el: continue
                preco = parse_preco(preco_el.get_text())
                if preco <= 0: continue
                
                orig = preco * 1.2
                orig_el = card.select_one('del') or card.select_one('s')
                if orig_el:
                    orig_val = parse_preco(orig_el.get_text())
                    if orig_val > preco:
                        orig = orig_val
                
                badge = card.select_one('[class*="discount"]')
                if badge and orig <= preco:
                    match = re.search(r'(\d+)%', badge.get_text())
                    if match:
                        pct = int(match.group(1))
                        if 1 <= pct <= 90:
                            orig = round(preco / (1 - pct/100), 2)
                
                desc, econ = calc_desconto(preco, orig)
                
                link_el = card.select_one('a[href]')
                if not link_el: continue
                link = link_el['href']
                if link.startswith('/'):
                    link = 'https://www.magazineluiza.com.br' + link
                link = aplicar_afiliado(link)
                
                img = None
                img_el = card.select_one('img')
                if img_el:
                    for attr in ['src', 'data-src']:
                        if img_el.get(attr):
                            img = img_el[attr]
                            if img.startswith('http'):
                                break
                
                produtos.append({
                    'id': hid(link),
                    'plataforma': 'MAGALU',
                    'plataforma_icone': '🔵',
                    'nome': nome,
                    'preco_original': round(orig, 2),
                    'preco_desconto': round(preco, 2),
                    'desconto': desc,
                    'economia': econ,
                    'link': link,
                    'imagem': img,
                })
            except: continue
    
    return produtos

# =============================================================================
# PLAYWRIGHT COLETOR PRINCIPAL
# =============================================================================

def coletar_com_playwright(urls: List[Tuple[str, str]]) -> int:
    """Coleta produtos de URLs usando Playwright."""
    if not urls: return 0
    total = 0
    browser = None
    
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-extensions",
                    "--disable-gpu"
                ]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1440, "height": 900},
                extra_http_headers={
                    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                }
            )
            
            page = context.new_page()
            page.set_default_timeout(TIMEOUT_PAGE)
            
            for url, plat in urls:
                if ciclo_cheio(): break
                
                log.info(f"🌐 [{plat}] {url[:80]}...")
                
                try:
                    # Navega
                    page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_PAGE)
                    
                    # Rola para carregar produtos
                    _scroll_page(page, vezes=4)
                    
                    # Pega HTML
                    html = page.content()
                    
                    # Extrai conforme plataforma
                    produtos = []
                    if plat == "MERCADO_LIVRE":
                        produtos = extrair_mercadolivre(html)
                    elif plat == "SHOPEE":
                        produtos = extrair_shopee(html)
                    elif plat == "ALIEXPRESS":
                        produtos = extrair_aliexpress(html)
                    elif plat == "AMAZON":
                        produtos = extrair_amazon(html)
                    elif plat == "MAGALU":
                        produtos = extrair_magalu(html)
                    
                    log.info(f"   📦 {len(produtos)} produtos brutos")
                    
                    # Processa produtos
                    for p in produtos:
                        if ciclo_cheio(): break
                        if processar(p):
                            total += 1
                    
                    if not ciclo_cheio():
                        time.sleep(DELAY_PLAYWRIGHT)
                        
                except PlaywrightTimeoutError:
                    log.warning(f"   ⚠️ Timeout em {url[:50]}")
                    continue
                except Exception as e:
                    log.warning(f"   ⚠️ Erro: {str(e)[:60]}")
                    continue
            
            browser.close()
            
    except Exception as e:
        log.error(f"Playwright: {str(e)[:100]}")
        if browser:
            try: browser.close()
            except: pass
    
    return total

# =============================================================================
# URLs POR PLATAFORMA
# =============================================================================

def gerar_urls() -> List[Tuple[str, str]]:
    """Gera URLs para TODAS as plataformas - VERSÃO EXPANDIDA."""
    urls = []
    
    # ==================== SHOPEE (MAIS URLs) ====================
    shopee_termos = [
        # Hardware
        "placa%20de%20video", "rtx%204060", "rtx%203060", "rx%206600", "rx%207600",
        "processador%20ryzen%205", "processador%20ryzen%207", "intel%20core%20i5",
        "intel%20core%20i7", "memoria%20ram%20ddr4%2016gb", "memoria%20ram%20ddr5",
        "ssd%20nvme%201tb", "ssd%20m2%201tb", "fonte%20650w", "fonte%20750w",
        "gabinete%20gamer", "water%20cooler%20240mm", "monitor%20gamer%20144hz",
        "teclado%20mecanico", "mouse%20gamer", "headset%20gamer", "notebook%20gamer",
        "pc%20gamer%20completo", "placa%20mae%20b550", "placa%20mae%20b660",
        
        # Eletrônicos
        "smart%20tv%2050", "smart%20tv%2055", "fone%20bluetooth", "caixa%20de%20som",
        "soundbar", "smartphone%20samsung", "smartphone%20xiaomi", "tablet",
        
        # Geral (ofertas)
        "air%20fryer", "cafeteira", "geladeira", "fogao", "maquina%20de%20lavar",
    ]
    
    for termo in shopee_termos:
        urls.append((f"https://shopee.com.br/search?keyword={termo}&sortBy=sales", "SHOPEE"))
        urls.append((f"https://shopee.com.br/search?keyword={termo}&sortBy=priceLowest", "SHOPEE"))
    
    # ==================== ALIEXPRESS (MAIS URLs) ====================
    aliexpress_termos = [
        # Hardware
        "gpu", "rtx%204060", "rtx%203060", "rx%206600", "graphics-card",
        "cpu", "ryzen%205", "ryzen%207", "intel%20i5", "intel%20i7",
        "ddr4%20ram%2016gb", "ddr5%20ram", "ssd%20nvme%201tb", "ssd%20m2",
        "power%20supply%20650w", "pc%20case", "water%20cooler", "gaming%20monitor",
        "mechanical%20keyboard", "gaming%20mouse", "gaming%20headset",
        
        # Eletrônicos
        "smart%20tv", "bluetooth%20earbuds", "smartwatch", "xiaomi%20phone",
    ]
    
    for termo in aliexpress_termos:
        urls.append((f"https://pt.aliexpress.com/w/wholesale-{termo}.html", "ALIEXPRESS"))
        urls.append((f"https://pt.aliexpress.com/w/wholesale-{termo}-best-price.html", "ALIEXPRESS"))
    
    # ==================== MERCADO LIVRE (MAIS URLs) ====================
    ml_termos = [
        "placa-de-video", "rtx-4060", "rtx-4070", "rtx-3060", "rx-7600", "rx-7700",
        "processador-ryzen-5", "processador-ryzen-7", "processador-i5", "processador-i7",
        "memoria-ram-ddr4-16gb", "memoria-ram-ddr5-32gb", "ssd-1tb-nvme", "ssd-2tb",
        "fonte-650w-80plus", "fonte-750w-modular", "gabinete-gamer-mid", "water-cooler-240mm",
        "monitor-gamer-144hz", "monitor-gamer-27", "teclado-mecanico-switch", "mouse-gamer",
        "headset-gamer-7.1", "notebook-gamer-rtx", "pc-gamer-completo", "placa-mae-b550",
        "smart-tv-4k-50", "smart-tv-4k-55", "fone-bluetooth-sports", "caixa-som-bluetooth",
        "air-fryer-digital", "cafeteira-expresso", "geladeira-inverter", "fogao-5-bocas",
    ]
    
    for termo in ml_termos:
        urls.append((f"https://lista.mercadolivre.com.br/{termo}", "MERCADO_LIVRE"))
        urls.append((f"https://lista.mercadolivre.com.br/{termo}_OrderId_PRICE", "MERCADO_LIVRE"))
    
    # ==================== AMAZON (MAIS URLs) ====================
    amazon_termos = [
        "placa+de+video", "rtx+4060", "rtx+4070", "rtx+3060", "rx+7600",
        "processador+ryzen+7", "processador+ryzen+5", "processador+i7", "processador+i5",
        "memoria+ram+ddr4+16gb", "memoria+ram+ddr5", "ssd+nvme+1tb", "fonte+650w",
        "gabinete+gamer", "water+cooler", "monitor+gamer+144hz", "teclado+mecanico",
        "mouse+gamer", "headset+gamer", "notebook+gamer", "pc+gamer",
        "smart+tv+4k+50", "fone+bluetooth", "caixa+de+som", "air+fryer",
    ]
    
    for termo in amazon_termos:
        urls.append((f"https://www.amazon.com.br/s?k={termo}&s=price-desc-rank", "AMAZON"))
        urls.append((f"https://www.amazon.com.br/s?k={termo}&s=relevanceblender", "AMAZON"))
    
    # ==================== MAGALU (MAIS URLs) ====================
    magalu_termos = [
        "placa-de-video", "processador", "memoria-ram", "ssd-nvme", "fonte-atx",
        "gabinete-gamer", "water-cooler", "monitor-gamer", "teclado-mecanico",
        "mouse-gamer", "headset-gamer", "notebook-gamer", "pc-gamer",
        "smart-tv-4k", "fone-bluetooth", "caixa-de-som", "air-fryer",
    ]
    
    for termo in magalu_termos:
        urls.append((f"https://www.magazineluiza.com.br/busca/{termo}/", "MAGALU"))
        urls.append((f"https://www.magazineluiza.com.br/busca/{termo}/?from=submit", "MAGALU"))
    
    # Embaralha
    random.shuffle(urls)
    log.info(f"📋 Total: {len(urls)} URLs geradas")
    return urls

# =============================================================================
# CICLO PRINCIPAL
# =============================================================================

def resetar_sessao():
    global _sessao
    with _lock:
        _sessao = {"HARDWARE": 0, "ELETRONICO": 0, "GERAL": 0, "total": 0}

def executar_ciclo(num: int):
    log.info(Fore.CYAN + f"\n{'='*60}" + Style.RESET_ALL)
    log.info(Fore.CYAN + f"  🔄 CICLO #{num} — {datetime.now().strftime('%d/%m %H:%M:%S')}" + Style.RESET_ALL)
    log.info(Fore.CYAN + f"{'='*60}" + Style.RESET_ALL)

    resetar_sessao()
    
    # Gera URLs
    urls = gerar_urls()
    
    # Coleta com Playwright
    log.info(Fore.CYAN + "🌐 Iniciando coleta Playwright..." + Style.RESET_ALL)
    total = coletar_com_playwright(urls[:50])  # Limite de 50 URLs por ciclo
    
    # Relatório
    t = _sessao["total"]
    cats = " | ".join(f"{c}:{n}" for c,n in _sessao.items() if c!="total" and n>0)
    log.info(Fore.GREEN + f"\n📊 Ciclo #{num} completo: {t} posts | {cats}" + Style.RESET_ALL)

def banner():
    print(Fore.CYAN + """
╔══════════════════════════════════════════════════════════════════════╗
║   🤖  ROBO HIBRIDO  v4.2  —  SHOPEE & ALIEXPRESS FIX               ║
║                                                                      ║
║   ✅  Shopee · AliExpress · Amazon · Magalu · Mercado Livre         ║
║   🔄  Loop INFINITO — nunca para sozinho                             ║
║   ✅  Preços REAIS com descontos confiáveis                         ║
║   ⚡  Envio IMEDIATO — achou → posta na hora                         ║
║   🛑  Ctrl+C para parar                                              ║
╚══════════════════════════════════════════════════════════════════════╝
    """ + Style.RESET_ALL)

def main():
    global _enviados, _modo_teste

    banner()
    _modo_teste = "test" in sys.argv

    _enviados = load_enviados()
    for item in load_historico():
        _historico.append(item)

    log.info(f"💾 {len(_enviados)} IDs | 📜 {len(_historico)} posts recentes")
    if _modo_teste:
        log.info(Fore.YELLOW + "🧪 MODO TESTE — não posta no Telegram" + Style.RESET_ALL)

    ciclo_num = 0

    while True:  # LOOP INFINITO
        ciclo_num += 1
        try:
            executar_ciclo(ciclo_num)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log.error(f"❌ Erro ciclo #{ciclo_num}: {e}")
            import traceback
            traceback.print_exc()

        log.info(Fore.YELLOW +
                 f"⏳ Aguardando {DELAY_CICLO//60} min para ciclo #{ciclo_num+1}... "
                 f"(Ctrl+C para parar)" + Style.RESET_ALL)

        # Espera em intervalos de 1 minuto
        for i in range(DELAY_CICLO // 60):
            try:
                time.sleep(60)
                restante = DELAY_CICLO//60 - i - 1
                if restante > 0 and restante % 2 == 0:
                    log.info(f"  ⏱ {restante} min para o próximo ciclo...")
            except KeyboardInterrupt:
                raise

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n\n⛔ Bot parado. Até logo!" + Style.RESET_ALL)
        try: 
            save_enviados()
            save_historico()
        except: pass
        sys.exit(0)