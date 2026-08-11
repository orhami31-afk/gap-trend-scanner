"""
watchlist.py
-------------
רשימת היקום שנסרק כל יום. כוללת ברירת מחדל של כ-300 מניות סחירות וגדולות
(S&P 500 + שמות בולטים מהנאסד"ק), שמכסה חלק ניכר מהנפח והנזילות בשוק
האמריקאי - אבל זו לא רשימה מלאה של 1000 מניות.

כדי להגיע ל-~1000 מניות בדיוק כמו שביקשת:
1. הורד רשימת טיקרים מלאה (S&P 500 + Russell 1000 + Nasdaq Composite) -
   אפשר מאתר הבורסה, מהברוקר שלך, או מ-Wikipedia (חינמי, מתעדכן).
2. שמור כקובץ CSV בשם tickers.csv באותה תיקייה, עמודה אחת בשם "symbol".
3. הקוד למטה טוען אוטומטית את הקובץ אם הוא קיים, ומשתמש בו במקום ברשימת
   ברירת המחדל.
"""

import os
import csv

_DEFAULT_WATCHLIST = [
    # מגה-קאפ טכנולוגיה ותקשורת
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA", "AVGO", "ORCL",
    "ADBE", "CRM", "CSCO", "ACN", "IBM", "INTU", "TXN", "QCOM", "AMD", "NOW",
    "AMAT", "MU", "LRCX", "KLAC", "SNPS", "CDNS", "PANW", "FTNT", "ANET", "APH",
    "NFLX", "CMCSA", "TMUS", "VZ", "T", "DIS", "WBD", "PARA", "SPOT", "RBLX",
    "UBER", "ABNB", "DASH", "SNAP", "PINS", "SHOP", "SQ", "PYPL", "COIN", "MSTR",
    "PLTR", "SNOW", "DDOG", "NET", "CRWD", "ZS", "OKTA", "TEAM", "WDAY", "MDB",
    "SMCI", "MARA", "RIOT", "APP", "TTD", "ROKU", "ETSY", "EBAY", "BKNG", "EXPE",
    # פיננסים
    "JPM", "BAC", "WFC", "C", "GS", "MS", "SCHW", "AXP", "BLK", "SPGI",
    "MMC", "CB", "PGR", "TRV", "ALL", "MET", "PRU", "AIG", "USB", "PNC",
    "TFC", "COF", "BK", "STT", "FITB", "HBAN", "RF", "KEY", "CFG", "MTB",
    "V", "MA", "FI", "FIS", "GPN", "ICE", "CME", "NDAQ", "MCO", "AON",
    # בריאות
    "UNH", "JNJ", "LLY", "PFE", "MRK", "ABBV", "TMO", "ABT", "DHR", "BMY",
    "AMGN", "GILD", "CVS", "CI", "ELV", "HUM", "ISRG", "SYK", "BSX", "MDT",
    "REGN", "VRTX", "ZTS", "BDX", "IDXX", "IQV", "MRNA", "BIIB", "HCA", "EW",
    # צריכה ותעשייה
    "WMT", "COST", "PG", "KO", "PEP", "MCD", "SBUX", "NKE", "HD", "LOW",
    "TGT", "TJX", "ROST", "YUM", "CMG", "MAR", "HLT", "LULU", "DG", "DLTR",
    "GM", "F", "HON", "GE", "CAT", "DE", "BA", "LMT", "RTX", "NOC",
    "UPS", "FDX", "UNP", "CSX", "NSC", "EMR", "ETN", "ITW", "PH", "CMI",
    "MMM", "DOW", "DD", "LIN", "APD", "ECL", "NEM", "FCX", "NUE", "STLD",
    # אנרגיה
    "XOM", "CVX", "COP", "SLB", "EOG", "PXD", "MPC", "PSX", "VLO", "OXY",
    "WMB", "KMI", "OKE", "HAL", "BKR", "DVN", "FANG", "HES", "CTRA", "MRO",
    # נדל"ן ותשתיות
    "AMT", "PLD", "CCI", "EQIX", "PSA", "SPG", "O", "WELL", "DLR", "AVB",
    # צמיחה / מניות "מעניינות" עם תנודתיות ונפח גבוה (רלוונטי לאסטרטגיית גאפ)
    "SOFI", "AFRM", "UPST", "LCID", "RIVN", "NIO", "XPEV", "LI", "CHPT", "BLNK",
    "SIRI", "GPRO", "PLUG", "FCEL", "BE", "ENPH", "SEDG", "RUN", "FSLR", "NOVA",
    "DKNG", "PENN", "MGM", "WYNN", "LVS", "CZR", "RCL", "CCL", "NCLH", "AAL",
    "DAL", "UAL", "LUV", "JBLU", "SAVE", "ALK",
    "GME", "AMC", "BB", "BBBY", "CVNA", "W", "CHWY", "PTON", "BYND", "OPEN",
    "SPCE", "JOBY", "ACHR", "IONQ", "RGTI", "QUBT", "SOUN", "BBAI", "AI", "PATH",
    # שבבים / חצי-מוליכים נוספים
    "ON", "MPWR", "SWKS", "QRVO", "MCHP", "ADI", "TER", "ENTG", "COHR", "WOLF",
    # ביומד / ביוטק ספקולטיבי
    "SAVA", "SRPT", "ALNY", "BMRN", "EXAS", "NTLA", "CRSP", "EDIT", "BEAM", "RARE",
]


def load_watchlist() -> list[str]:
    csv_path = os.path.join(os.path.dirname(__file__), "tickers.csv")
    if os.path.exists(csv_path):
        symbols = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = (row.get("symbol") or "").strip().upper()
                if sym:
                    symbols.append(sym)
        if symbols:
            return sorted(set(symbols))
    return _DEFAULT_WATCHLIST


WATCHLIST = load_watchlist()
