#!/usr/bin/env python3
"""Curated Indian sector -> NSE tickers (Yahoo format) map for the screen web app.

`fit` describes how well a sector suits the 47 operational criteria (margins,
ROCE/ROE, interest coverage, current ratio, D/E, CFO, net-debt/EBITDA):
- industrial  : good fit (operating cash-flow + return-on-capital businesses)
- financial   : poor fit (leverage is structural; use a banks-specific registry)
- high-debt   : poor fit (capex/leverage are structural)
"""

AND = " & "
SECTORS: dict[str, dict] = {
    "Pharmaceuticals": {"fit": "industrial", "tickers": [
        "SUNPHARMA.NS", "DIVISLAB.NS", "CIPLA.NS", "LUPIN.NS", "DRREDDY.NS",
        "ZYDUSLIFE.NS", "AUROPHARMA.NS", "TORNTPHARM.NS", "BIOCON.NS",
        "GLENMARK.NS", "IPCALAB.NS", "ALKYLAMINE.NS"]},
    "IT Services": {"fit": "industrial", "tickers": [
        "TCS.NS", "INFY.NS", "TATATECH.NS", "WIPRO.NS", "KPITTECH.NS",
        "TECHM.NS", "COFORGE.NS", "PERSISTENT.NS", "MPHASIS.NS", "OFSS.NS"]},
    "Consumer / FMCG": {"fit": "industrial", "tickers": [
        "HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS", "DABUR.NS",
        "GODREJCP.NS", "TATACONSUM.NS", "MARICO.NS", "COLPAL.NS", "EMAMILTD.NS"]},
    "Automobiles": {"fit": "industrial", "tickers": [
        "MARUTI.NS", "TATAMOTORS.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS",
        "HEROMOTOCO.NS", "TVSMOTOR.NS", "ASHOKLEY.NS", "BHARATFORG.NS"]},
    "Chemicals": {"fit": "industrial", "tickers": [
        "SRF.NS", "UPL.NS", "PIIND.NS", "AARTIIND.NS", "NAVINFLUOR.NS",
        "DEEPAKNTR.NS", "TATACHEM.NS", "GNFC.NS", "VINATIORGA.NS", "CHAMBLFERT.NS"]},
    "Cement": {"fit": "industrial", "tickers": [
        "ULTRACEMCO.NS", "GRASIM.NS", "AMBUJACEM.NS", "ACC.NS", "DALBHARAT.NS",
        "JKCEMENT.NS", "SHREECEM.NS", "RAMCOCEM.NS"]},
    "Capital Goods / Infra": {"fit": "industrial", "tickers": [
        "LT.NS", "SIEMENS.NS", "ABB.NS", "CUMMINSIND.NS", "BHEL.NS",
        "HAVELLS.NS", "BEL.NS", "THERMAX.NS", "KEC.NS", "NCC.NS"]},
    "Metals & Mining": {"fit": "industrial", "tickers": [
        "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "VEDL.NS", "SAIL.NS",
        "NMDC.NS", "JINDALSTEL.NS", "NATIONALUM.NS", "HINDZINC.NS"]},
    "Oil & Gas": {"fit": "high-debt", "tickers": [
        "RELIANCE.NS", "ONGC.NS", "BPCL.NS", "IOC.NS", "GAIL.NS",
        "HPCL.NS", "PETRONET.NS"]},
    "Power / Utilities": {"fit": "high-debt", "tickers": [
        "NTPC.NS", "POWERGRID.NS", "TATAPOWER.NS", "JSWENERGY.NS",
        "TORNTPOWER.NS", "CESC.NS"]},
    "Telecom": {"fit": "high-debt", "tickers": [
        "BHARTIARTL.NS", "IDEA.NS", "TATACOMM.NS", "INDUSTOWERS.NS"]},
    "Private Banks": {"fit": "financial", "tickers": [
        "HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "AXISBANK.NS",
        "INDUSINDBK.NS", "FEDERALBNK.NS", "IDFCFIRSTB.NS", "AUBANK.NS", "BANDHANBNK.NS"]},
    "PSU Banks": {"fit": "financial", "tickers": [
        "SBIN.NS", "BANKBARODA.NS", "PNB.NS", "CANBK.NS", "UNIONBANK.NS",
        "IOB.NS", "MAHABANK.NS", "CENTRALBK.NS"]},
    "NBFC / Financial Services": {"fit": "financial", "tickers": [
        "BAJFINANCE.NS", "BAJAJFINSV.NS", "CHOLAFIN.NS", "MUTHOOTFIN.NS",
        "LICHSGFIN.NS", "MANAPPURAM.NS", "SBICARD.NS", "SHRIRAMFIN.NS"]},
    "Healthcare & Pharmaceuticals": {"fit": "industrial", "tickers": [
        "SUNPHARMA.NS", "DIVISLAB.NS", "CIPLA.NS", "LUPIN.NS", "DRREDDY.NS",
        "ZYDUSLIFE.NS", "AUROPHARMA.NS", "TORNTPHARM.NS", "BIOCON.NS",
        "APOLLOHOSP.NS", "MAXHEALTH.NS", "FORTIS.NS", "LALPATHLAB.NS",
        "LAURUSLABS.NS", "MANKIND.NS", "GLAND.NS", "ALKYLAMINE.NS"]},
    "Infrastructure, Construction & Real Estate": {"fit": "industrial", "tickers": [
        "LT.NS", "NCC.NS", "KEC.NS", "RVNL.NS", "IRCON.NS",
        "DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "PRESTIGE.NS", "LODHA.NS", "SOBHA.NS"]},
    "Automobile & Auto Components": {"fit": "industrial", "tickers": [
        "MARUTI.NS", "TVSMOTOR.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "ASHOKLEY.NS",
        "BHARATFORG.NS", "MOTHERSON.NS", "BOSCHLTD.NS", "UNOMINDA.NS",
        "EXIDEIND.NS", "APOLLOTYRE.NS", "TIINDIA.NS"]},
    "Information Technology & Digital": {"fit": "industrial", "tickers": [
        "TCS.NS", "INFY.NS", "TATATECH.NS", "WIPRO.NS", "KPITTECH.NS",
        "TECHM.NS", "COFORGE.NS", "PERSISTENT.NS", "MPHASIS.NS", "OFSS.NS",
        "ZENSARTECH.NS", "TATAELXSI.NS"]},
    "Capital Goods & Industrials": {"fit": "industrial", "tickers": [
        "SIEMENS.NS", "ABB.NS", "CUMMINSIND.NS", "BHEL.NS", "HAVELLS.NS",
        "BEL.NS", "THERMAX.NS", "KEC.NS", "NCC.NS", "POLYCAB.NS", "ASTRAL.NS", "CYIENT.NS"]},
    "Oil, Gas & Consumable Fuels": {"fit": "high-debt", "tickers": [
        "RELIANCE.NS", "ONGC.NS", "BPCL.NS", "IOC.NS", "GAIL.NS",
        "HPCL.NS", "PETRONET.NS", "OIL.NS", "MRPL.NS", "GSPL.NS"]},
    "Telecom & Media": {"fit": "high-debt", "tickers": [
        "BHARTIARTL.NS", "IDEA.NS", "TATACOMM.NS", "INDUSTOWERS.NS",
        "SUNTV.NS", "PVRINOX.NS", "ZEEL.NS"]},
    "Power & Utilities": {"fit": "high-debt", "tickers": [
        "NTPC.NS", "POWERGRID.NS", "TATAPOWER.NS", "JSWENERGY.NS",
        "TORNTPOWER.NS", "CESC.NS", "NHPC.NS", "SJVN.NS", "ADANIPOWER.NS"]},
    "Transport Infrastructure & Logistics": {"fit": "high-debt", "tickers": [
        "ADANIPORTS.NS", "CONCOR.NS", "GMRINFRA.NS", "IRB.NS", "RVNL.NS",
        "JSWINFRA.NS", "INDIGO.NS"]},
    "Chemicals & Materials": {"fit": "industrial", "tickers": [
        "SRF.NS", "UPL.NS", "PIIND.NS", "AARTIIND.NS", "NAVINFLUOR.NS",
        "DEEPAKNTR.NS", "TATACHEM.NS", "GNFC.NS", "VINATIORGA.NS",
        "CHAMBLFERT.NS", "PIDILITIND.NS", "ASIANPAINT.NS"]},
}

FIT_NOTES = {
    "financial": ("Banks/NBFCs are screened with a bank-specific registry (ROE, ROA, "
                  "equity / assets, gross NPA, growth, P/E, P/B) instead of the 47 "
                  "operational criteria. NIM and cost-to-income are not reliably "
                  "reported, and Gross NPA can be masked (then treated as missing)."),
    "high-debt": ("This sector is capital-intensive with structurally higher "
                  "leverage; debt/leverage and FCF criteria are stricter than "
                  "is fair. Treat results with that lens."),
}


def sector_names() -> list[str]:
    return list(SECTORS.keys())


def get_tickers(sector: str) -> list[str] | None:
    if sector == "Custom":
        return None
    entry = SECTORS.get(sector)
    return list(entry["tickers"]) if entry else None


def get_fit(sector: str) -> str:
    entry = SECTORS.get(sector)
    return entry["fit"] if entry else "industrial"


def get_fit_note(sector: str) -> str:
    return FIT_NOTES.get(get_fit(sector), "")
