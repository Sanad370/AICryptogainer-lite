import os
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import uuid
# New imports for the conversion logic
import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode

# Initialize Binance
exchange = ccxt.binance({
    'apiKey': os.environ['API'],  # Replace with your actual API key
    'secret': os.environ['SECRET'],  # Replace with your actual secret
    'sandbox': False,  # Set to True for testnet
    'enableRateLimit': True,
})

# +++ START OF NEW CONVERSION LOGIC (from test_convert.py) +++
BASE_URL = 'https://api.binance.com'
headers = {
    'X-MBX-APIKEY': exchange.apiKey
}

def get_signature(query_string: str) -> str:
    """Generates the HMAC SHA256 signature for a query string."""
    return hmac.new(exchange.secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

def get_quote(from_asset, to_asset, amount):
    """Gets a quote for a conversion."""
    endpoint = '/sapi/v1/convert/getQuote'
    url = f'{BASE_URL}{endpoint}'
    
    params = {
        'fromAsset': from_asset,
        'toAsset': to_asset,
        'fromAmount': amount,
        'timestamp': int(time.time() * 1000)
    }

    query_string = urlencode(params)
    params['signature'] = get_signature(query_string)

    response = requests.post(url, headers=headers, data=params)
    return response.json()

def accept_quote(quote_id):
    """Accepts a previously received quote to execute the conversion."""
    endpoint = '/sapi/v1/convert/acceptQuote'
    url = f'{BASE_URL}{endpoint}'

    params = {
        'quoteId': quote_id,
        'timestamp': int(time.time() * 1000)
    }
    
    query_string = urlencode(params)
    params['signature'] = get_signature(query_string)

    response = requests.post(url, headers=headers, data=params)
    return response.json()
# +++ END OF NEW CONVERSION LOGIC +++


class PatternRegistry:
    """Registry to manage candlestick patterns and their detection functions"""

    def __init__(self):
        self.patterns = []

    def register(self, name, detection_func, candle_count, is_bullish, is_bearish):
        """Register a pattern with its detection function and properties"""
        self.patterns.append({
            'name': name,
            'func': detection_func,
            'candle_count': candle_count,
            'is_bullish': is_bullish,
            'is_bearish': is_bearish
        })

    def get_required_candles(self):
        """Return the maximum number of candles needed by any pattern"""
        return max(pattern['candle_count'] for pattern in self.patterns) if self.patterns else 1

    def detect_all(self, ohlc_data, trend):
        """Detect all registered patterns and return scores"""
        scores = {}
        for pattern in self.patterns:
            if len(ohlc_data) < pattern['candle_count']:
                scores[pattern['name']] = 0.0
                continue
            if pattern['candle_count'] == 1:
                score = pattern['func'](ohlc_data[-1], trend=trend) if 'trend' in pattern[
                    'func'].__code__.co_varnames else pattern['func'](ohlc_data[-1])
            elif pattern['candle_count'] == 2:
                score = pattern['func'](ohlc_data[-2], ohlc_data[-1])
            else:
                score = pattern['func'](ohlc_data[-pattern['candle_count']:])
            scores[pattern['name']] = score
        return scores


# Initialize pattern registry
pattern_registry = PatternRegistry()


# Candlestick Pattern Detection Functions
def detect_hammer(ohlc):
    """Detect Hammer pattern"""
    body = abs(ohlc['close'] - ohlc['open'])
    total_range = ohlc['high'] - ohlc['low']
    if total_range == 0:
        return 0.0
    wick_lower = min(ohlc['open'], ohlc['close']) - ohlc['low']
    wick_upper = ohlc['high'] - max(ohlc['open'], ohlc['close'])
    return 0.8 if (wick_lower > 2 * body and wick_upper < body and body < total_range * 0.3) else 0.0


def detect_hanging_man(ohlc, trend='up'):
    """Detect Hanging Man pattern (hammer in uptrend)"""
    return detect_hammer(ohlc) if trend == 'up' else 0.0


def detect_inverted_hammer(ohlc):
    """Detect Inverted Hammer pattern"""
    body = abs(ohlc['close'] - ohlc['open'])
    total_range = ohlc['high'] - ohlc['low']
    if total_range == 0:
        return 0.0
    wick_upper = ohlc['high'] - max(ohlc['open'], ohlc['close'])
    wick_lower = min(ohlc['open'], ohlc['close']) - ohlc['low']
    return 0.8 if (wick_upper > 2 * body and wick_lower < body and body < total_range * 0.3) else 0.0


def detect_shooting_star(ohlc, trend='up'):
    """Detect Shooting Star pattern (inverted hammer in uptrend)"""
    return detect_inverted_hammer(ohlc) if trend == 'up' else 0.0


def detect_doji(ohlc):
    """Detect Doji pattern"""
    body = abs(ohlc['close'] - ohlc['open'])
    total_range = ohlc['high'] - ohlc['low']
    if total_range == 0:
        return 0.0
    return 0.7 if body < total_range * 0.1 else 0.0


def detect_spinning_top(ohlc):
    """Detect Spinning Top pattern"""
    body = abs(ohlc['close'] - ohlc['open'])
    total_range = ohlc['high'] - ohlc['low']
    if total_range == 0:
        return 0.0
    wick_upper = ohlc['high'] - max(ohlc['open'], ohlc['close'])
    wick_lower = min(ohlc['open'], ohlc['close']) - ohlc['low']
    return 0.6 if (body < total_range * 0.3 and wick_upper > body and wick_lower > body) else 0.0


def detect_marubozu(ohlc):
    """Detect Marubozu pattern (long candle with no shadows)"""
    body = abs(ohlc['close'] - ohlc['open'])
    total_range = ohlc['high'] - ohlc['low']
    if total_range == 0:
        return 0.0
    is_white = ohlc['close'] > ohlc['open'] and ohlc['high'] - ohlc['close'] < body * 0.1 and ohlc['open'] - ohlc[
        'low'] < body * 0.1
    is_black = ohlc['close'] < ohlc['open'] and ohlc['high'] - ohlc['open'] < body * 0.1 and ohlc['close'] - ohlc[
        'low'] < body * 0.1
    return 0.9 if is_white or is_black else 0.0


def detect_bullish_engulfing(ohlc_prev, ohlc_curr):
    """Detect Bullish Engulfing pattern"""
    prev_bearish = ohlc_prev['close'] < ohlc_prev['open']
    curr_bullish = ohlc_curr['close'] > ohlc_curr['open']
    if prev_bearish and curr_bullish:
        engulfs = (ohlc_curr['open'] < ohlc_prev['close'] and ohlc_curr['close'] > ohlc_prev['open'])
        return 0.9 if engulfs else 0.0
    return 0.0


def detect_bearish_engulfing(ohlc_prev, ohlc_curr):
    """Detect Bearish Engulfing pattern"""
    prev_bullish = ohlc_prev['close'] > ohlc_prev['open']
    curr_bearish = ohlc_curr['close'] < ohlc_curr['open']
    if prev_bullish and curr_bearish:
        engulfs = (ohlc_curr['open'] > ohlc_prev['close'] and ohlc_curr['close'] < ohlc_prev['open'])
        return 0.9 if engulfs else 0.0
    return 0.0


def detect_bullish_harami(ohlc_prev, ohlc_curr):
    """Detect Bullish Harami pattern"""
    prev_bearish = ohlc_prev['close'] < ohlc_prev['open']
    curr_bullish = ohlc_curr['close'] > ohlc_curr['open']
    if prev_bearish and curr_bullish:
        prev_body = abs(ohlc_prev['close'] - ohlc_prev['open'])
        curr_body = abs(ohlc_curr['close'] - ohlc_curr['open'])
        return 0.7 if curr_body < prev_body * 0.5 and ohlc_curr['open'] > ohlc_prev['open'] and ohlc_curr['close'] < \
                      ohlc_prev['close'] else 0.0
    return 0.0


def detect_dark_cloud_cover(ohlc_prev, ohlc_curr):
    """Detect Dark Cloud Cover pattern"""
    prev_bullish = ohlc_prev['close'] > ohlc_prev['open']
    curr_bearish = ohlc_curr['close'] < ohlc_curr['open']
    if prev_bullish and curr_bearish:
        curr_body = abs(ohlc_curr['open'] - ohlc_curr['close'])
        prev_body = abs(ohlc_prev['open'] - ohlc_prev['close'])
        penetrates = ohlc_curr['close'] < (ohlc_prev['open'] + ohlc_prev['close']) / 2
        return 0.85 if (ohlc_curr['open'] > ohlc_prev['high'] and penetrates and curr_body > prev_body * 0.5) else 0.0
    return 0.0


def detect_morning_star(ohlc_list):
    """Detect Morning Star pattern (3 candles)"""
    if len(ohlc_list) < 3:
        return 0.0
    first, second, third = ohlc_list[-3], ohlc_list[-2], ohlc_list[-1]
    first_bearish = first['close'] < first['open']
    second_small_body = abs(second['close'] - second['open']) < (second['high'] - second['low']) * 0.3
    third_bullish = third['close'] > third['open']
    third_recovery = third['close'] > (first['open'] + first['close']) / 2
    return 0.95 if (first_bearish and second_small_body and third_bullish and third_recovery) else 0.0


def detect_evening_star(ohlc_list):
    """Detect Evening Star pattern (3 candles)"""
    if len(ohlc_list) < 3:
        return 0.0
    first, second, third = ohlc_list[-3], ohlc_list[-2], ohlc_list[-1]
    first_bullish = first['close'] > first['open']
    second_small_body = abs(second['close'] - second['open']) < (second['high'] - second['low']) * 0.3
    third_bearish = third['close'] < third['open']
    third_decline = third['close'] < (first['open'] + first['close']) / 2
    return 0.95 if (first_bullish and second_small_body and third_bearish and third_decline) else 0.0


def detect_three_white_soldiers(ohlc_list):
    """Detect Three White Soldiers pattern"""
    if len(ohlc_list) < 3:
        return 0.0
    first, second, third = ohlc_list[-3], ohlc_list[-2], ohlc_list[-1]
    first_bullish = first['close'] > first['open']
    second_bullish = second['close'] > second['open']
    third_bullish = third['close'] > third['open']
    return 0.9 if (first_bullish and second_bullish and third_bullish and
                   second['open'] > first['close'] and third['open'] > second['close'] and
                   third['close'] > second['close']) else 0.0


def detect_abandoned_baby(ohlc_list, trend='down'):
    """Detect Abandoned Baby pattern (3 candles)"""
    if len(ohlc_list) < 3:
        return 0.0
    first, second, third = ohlc_list[-3], ohlc_list[-2], ohlc_list[-1]
    if trend == 'down':
        first_bearish = first['close'] < first['open']
        second_doji = abs(second['close'] - second['open']) < (second['high'] - second['low']) * 0.1
        third_bullish = third['close'] > third['open']
        gap_down = second['high'] < first['low']
        gap_up = third['low'] > second['high']
        return 0.95 if (first_bearish and second_doji and third_bullish and gap_down and gap_up) else 0.0
    else:  # Uptrend for bearish Abandoned Baby
        first_bullish = first['close'] > first['open']
        second_doji = abs(second['close'] - second['open']) < (second['high'] - second['low']) * 0.1
        third_bearish = third['close'] < third['open']
        gap_up = second['low'] > first['high']
        gap_down = third['high'] < second['low']
        return 0.95 if (first_bullish and second_doji and third_bearish and gap_up and gap_down) else 0.0


def detect_downside_tasuki_gap(ohlc_list):
    """Detect Downside Tasuki Gap pattern (3 candles)"""
    if len(ohlc_list) < 3:
        return 0.0
    first, second, third = ohlc_list[-3], ohlc_list[-2], ohlc_list[-1]
    first_bearish = first['close'] < first['open']
    second_bearish = second['close'] < second['open']
    third_bullish = third['close'] > third['open']
    gap_down = second['high'] < first['low']
    third_in_gap = third['open'] > second['close'] and third['close'] < first['close']
    return 0.85 if (first_bearish and second_bearish and third_bullish and gap_down and third_in_gap) else 0.0


# Register patterns
pattern_registry.register('Hammer', detect_hammer, 1, True, False)
pattern_registry.register('Hanging Man', detect_hanging_man, 1, False, True)
pattern_registry.register('Inverted Hammer', detect_inverted_hammer, 1, True, False)
pattern_registry.register('Shooting Star', detect_shooting_star, 1, False, True)
pattern_registry.register('Doji', detect_doji, 1, True, True)
pattern_registry.register('Spinning Top', detect_spinning_top, 1, True, True)
pattern_registry.register('Marubozu', detect_marubozu, 1, True, True)
pattern_registry.register('Bullish Engulfing', detect_bullish_engulfing, 2, True, False)
pattern_registry.register('Bearish Engulfing', detect_bearish_engulfing, 2, False, True)
pattern_registry.register('Bullish Harami', detect_bullish_harami, 2, True, False)
pattern_registry.register('Dark Cloud Cover', detect_dark_cloud_cover, 2, False, True)
pattern_registry.register('Morning Star', detect_morning_star, 3, True, False)
pattern_registry.register('Evening Star', detect_evening_star, 3, False, True)
pattern_registry.register('Three White Soldiers', detect_three_white_soldiers, 3, True, False)
pattern_registry.register('Abandoned Baby', detect_abandoned_baby, 3, True, True)
pattern_registry.register('Downside Tasuki Gap', detect_downside_tasuki_gap, 3, False, True)


# TODO: Add more patterns here following the same structure
# Example for adding a new pattern:
# def detect_new_pattern(ohlc_list):
#     # Logic for new pattern
#     return score
# pattern_registry.register('New Pattern', detect_new_pattern, candle_count, is_bullish, is_bearish)

def detect_trend(ohlc_data, periods=5):
    """Simple trend detection based on closing prices"""
    if len(ohlc_data) < periods:
        return 'neutral'
    recent_closes = [candle['close'] for candle in ohlc_data[-periods:]]
    if recent_closes[-1] > recent_closes[0] * 1.02:  # 2% increase
        return 'up'
    elif recent_closes[-1] < recent_closes[0] * 0.98:  # 2% decrease
        return 'down'
    else:
        return 'neutral'


def calculate_pattern_score(ohlc_data):
    """Calculate aggregate pattern score with all registered patterns"""
    if len(ohlc_data) < pattern_registry.get_required_candles():
        return 0.0
    trend = detect_trend(ohlc_data)
    pattern_scores = pattern_registry.detect_all(ohlc_data, trend)

    score = 0.0
    for pattern in pattern_registry.patterns:
        pattern_score = pattern_scores[pattern['name']]
        if pattern_score > 0:
            # Trend strength multiplier based on 24h price change
            price_change_24h = ((ohlc_data[-1]['close'] - ohlc_data[0]['close']) / ohlc_data[0]['close']) * 100
            trend_strength = max(1.0, min(2.0, 1.0 + abs(price_change_24h) / 20))  # Cap at 2x for ±20% change
            if trend == 'up' and pattern['is_bullish']:
                score += pattern_score * trend_strength * 1.2
            elif trend == 'down' and pattern['is_bearish']:
                score += pattern_score * trend_strength * 1.2
            elif trend == 'neutral':
                score += pattern_score * 0.8
            else:
                score += pattern_score * 0.5
    # Normalize score to 0-100 range
    num_patterns = len(pattern_registry.patterns)
    return min(100.0, max(0.0, score * (25 / max(1, num_patterns / 10))))


def analyze_single_pair(pair, limit=10):
    """Analyze a single trading pair with improved error handling"""
    try:
        ohlcv = exchange.fetch_ohlcv(pair, timeframe='4h', limit=max(limit, pattern_registry.get_required_candles()))
        if len(ohlcv) < pattern_registry.get_required_candles():
            return None
        ohlc_data = [{'timestamp': candle[0], 'open': float(candle[1]), 'high': float(candle[2]),
                      'low': float(candle[3]), 'close': float(candle[4]), 'volume': float(candle[5])}
                     for candle in ohlcv]
        score = calculate_pattern_score(ohlc_data)
        trend = detect_trend(ohlc_data)
        current_price = ohlc_data[-1]['close']
        volume_24h = sum([c['volume'] for c in ohlc_data[-6:]])
        price_change_24h = ((ohlc_data[-1]['close'] - ohlc_data[0]['close']) / ohlc_data[0]['close']) * 100
        return {
            'pair': pair, 'score': score, 'trend': trend, 'current_price': current_price,
            'volume_24h': volume_24h, 'price_change_24h': price_change_24h, 'last_updated': datetime.now(),
            'patterns_detected': pattern_registry.detect_all(ohlc_data, trend)
        }
    except (ccxt.NetworkError, ccxt.ExchangeError) as e:
        print(f"Error for {pair}: {e}")
        return None
    except Exception:
        return None


def get_best_coins(top_n=10):
    """Get best coins based on candlestick pattern analysis, only USDT pairs"""
    print("Loading markets...")
    markets = exchange.load_markets()
    spot_pairs = [pair for pair in markets
                  if markets[pair]['spot'] and markets[pair]['active']
                  and pair.endswith(('/USDT'))]
    excluded = ['USDT/USDT', 'USDC/USDT', 'USDT/USDC', 'USDC/USDC', 'BUSD/USDT', 'TUSD/USDT', 'DAI/USDT', 'FDUSD/USDT']
    spot_pairs = [pair for pair in spot_pairs if pair not in excluded]
    print(f"Found {len(spot_pairs)} active USDT spot trading pairs")
    print(f"Analyzing {len(spot_pairs)} pairs for patterns...")
    results, failed_pairs = [], []
    for i, pair in enumerate(spot_pairs):
        if i % 50 == 0:
            print(f"Progress: {i}/{len(spot_pairs)} pairs ({i / len(spot_pairs) * 100:.1f}%)")
        result = analyze_single_pair(pair)
        if result and result['score'] > 0:
            results.append(result)
        elif result is None:
            failed_pairs.append(pair)
    print(f"\n✅ Analysis Complete! 📊 {len(results)} pairs analyzed, ❌ {len(failed_pairs)} failed, "
          f"🎯 {len([r for r in results if r['score'] > 20])} with signals")
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_n]


def print_analysis_results(results):
    """Print formatted analysis results"""
    print("\n" + "=" * 90)
    print("🚀 TOP CRYPTO INVESTMENT OPPORTUNITIES (Next 4 Hours) - USDT PAIRS")
    print("=" * 90)
    if not results:
        print("No significant patterns detected.")
        return
    for i, result in enumerate(results, 1):
        trend_emoji = "📈" if result['trend'] == 'up' else "📉" if result['trend'] == 'down' else "➡️"
        price_format = f"${result['current_price']:,.4f}"
        change_emoji = "🟢" if result.get('price_change_24h', 0) > 0 else "🔴" if result.get('price_change_24h',
                                                                                           0) < 0 else "⚪"
        print(f"\n{i}. {result['pair']} {trend_emoji}")
        print(f"   📊 Pattern Score: {result['score']:.1f}% 🎯")
        print(f"   💰 Current Price: {price_format}")
        print(f"   📈 24h Change: {result.get('price_change_24h', 0):+.2f}% {change_emoji}")
        print(f"   🔄 Trend: {result['trend'].upper()}")
        print(f"   📦 24h Volume: {result['volume_24h']:,.2f}")
        print(f"   ⏰ Analysis Time: {result['last_updated'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   🔍 Patterns Detected: {', '.join([k for k, v in result['patterns_detected'].items() if v > 0])}")


def get_market_summary(results):
    """Print market summary statistics"""
    if not results:
        return
    print(f"\n{'=' * 60}")
    print("📋 MARKET ANALYSIS SUMMARY")
    print("=" * 60)
    usdt_pairs = len([r for r in results if r['pair'].endswith('/USDT')])
    print(f"💲 USDT Pairs: {usdt_pairs}")
    uptrend, downtrend, neutral = len([r for r in results if r['trend'] == 'up']), \
        len([r for r in results if r['trend'] == 'down']), \
        len([r for r in results if r['trend'] == 'neutral'])
    print(f"\n📊 TREND DISTRIBUTION: 📈 {uptrend}, 📉 {downtrend}, ➡️ {neutral}")
    avg_score = sum([r['score'] for r in results]) / len(results) if results else 0
    max_score = max([r['score'] for r in results]) if results else 0
    print(
        f"\n🎯 PATTERN SCORES: Avg {avg_score:.1f}%, Max {max_score:.1f}%, >50% {len([r for r in results if r['score'] > 50])}, 20-50% {len([r for r in results if 20 < r['score'] <= 50])}")


def analyze_btc_detailed():
    """Detailed analysis of BTC/USDT"""
    print("\n" + "=" * 60)
    print("🔍 DETAILED BTC/USDT PATTERN ANALYSIS")
    print("=" * 60)
    result = analyze_single_pair('BTC/USDT', limit=10)
    if not result:
        print("Could not analyze BTC/USDT")
        return
    print(f"Overall Score: {result['score']:.1f}%")
    print(f"Trend: {result['trend'].upper()}")
    print(f"Current Price: ${result['current_price']:,.2f}")
    print(f"\n📊 Individual Pattern Scores:")
    for pattern_name, score in result['patterns_detected'].items():
        if score > 0:
            print(f"{pattern_name}: {score:.1f}")


def get_wallet_balances():
    """Get all non-zero balances in spot wallet"""
    try:
        balance = exchange.fetch_balance()
        non_zero_balances = {}
        if isinstance(balance, dict):
            for asset, amounts in balance.items():
                if asset not in ['info', 'free', 'used', 'total', 'datetime', 'timestamp']:
                    total_amount = amounts.get('total', 0) if isinstance(amounts, dict) else amounts
                    if total_amount > 0:
                        non_zero_balances[asset] = amounts if isinstance(amounts, dict) else {'total': total_amount,
                                                                                              'free': total_amount,
                                                                                              'used': 0}
        return non_zero_balances
    except Exception as e:
        print(f"Error fetching wallet balance: {e}")
        try:
            print("Trying alternative method...")
            account = exchange.fetch_account()
            if 'balances' in account:
                balances = account['balances']
                non_zero_balances = {
                    b['asset']: {'total': float(b['free']) + float(b['locked']), 'free': float(b['free']),
                                 'used': float(b['locked'])} for b in balances if
                    float(b['free']) + float(b['locked']) > 0}
                return non_zero_balances
        except Exception as e2:
            print(f"Alternative method failed: {e2}")
        return {}


# --- REWRITTEN TRADING FUNCTIONS ---
def convert_to_usdt(asset, amount):
    """Convert an asset to USDT using the get/accept quote method."""
    print(f"🔄 Attempting to convert {amount:.6f} {asset} to USDT via quote...")
    try:
        # Minimum checks (can be enhanced with API calls if needed)
        # For simplicity, we assume amounts are reasonable for conversion
        quote = get_quote(asset, 'USDT', amount)
        if 'quoteId' in quote:
            print(f"✅ Quote received to convert {asset} to USDT.")
            # print(f"Quote details: {quote}") # Uncomment for debugging
            result = accept_quote(quote['quoteId'])
            # --- MODIFIED LINE: Check for 'orderStatus' instead of 'status' ---
            if result.get('orderStatus') in ['PROCESS', 'SUCCESS']:
                print(f"✅ Conversion successful: {amount:.6f} {asset} -> {result.get('toAmount')} USDT. Order ID: {result.get('orderId')}")
                return True
            else:
                print(f"❌ Conversion failed after quote acceptance: {result.get('message', result)}")
                return False
        else:
            print(f"❌ Failed to get quote for {asset}/USDT: {quote.get('msg', quote)}")
            return False
    except Exception as e:
        print(f"❌ Exception during USDT conversion for {asset}: {e}")
        return False


def buy_asset_with_usdt(pair, usdt_amount):
    """Buy an asset using USDT via the get/accept quote method."""
    print(f"🔄 Attempting to buy {pair} with {usdt_amount:.2f} USDT via quote...")
    base_asset = pair.split('/')[0]
    try:
        # Minimum cost check
        markets = exchange.load_markets()
        market = markets.get(pair)
        if market:
            min_cost = market.get('limits', {}).get('cost', {}).get('min', 10)
            if usdt_amount < min_cost:
                print(f"❌ Amount ${usdt_amount:.2f} below minimum trade size of ${min_cost} for {pair}")
                return False

        quote = get_quote('USDT', base_asset, usdt_amount)
        if 'quoteId' in quote:
            print(f"✅ Quote received to buy {base_asset} with USDT.")
            # print(f"Quote details: {quote}") # Uncomment for debugging
            result = accept_quote(quote['quoteId'])
            # --- MODIFIED LINE: Check for 'orderStatus' instead of 'status' ---
            if result.get('orderStatus') in ['PROCESS', 'SUCCESS']:
                print(f"✅ Purchase successful: {usdt_amount:.2f} USDT -> {result.get('toAmount')} {base_asset}. Order ID: {result.get('orderId')}")
                return True
            else:
                print(f"❌ Purchase failed after quote acceptance: {result.get('message', result)}")
                return False
        else:
            print(f"❌ Failed to get quote for {pair}: {quote.get('msg', quote)}")
            return False
    except Exception as e:
        print(f"❌ Exception during asset purchase for {pair}: {e}")
        return False


def convert_small_balances_to_bnb(small_balances):
    """Convert small balances to BNB using Binance's Convert Low-Value Assets to BNB"""
    try:
        if not small_balances:
            print("No small balances to convert to BNB")
            return False
        # Skip if only USDT and BNB are present as small balances
        if all(asset in ['USDT', 'BNB'] for asset in small_balances.keys()):
            print("🟡 Skipping dust conversion: Only USDT and BNB detected as small balances")
            return False
        asset_list = ','.join(small_balances.keys())
        params = {'asset': asset_list, 'recvWindow': 5000}
        response = exchange.fetch('sapi/v1/asset/dust', 'private', 'POST', params)
        print(f"Debug: Dust conversion raw response={response}")  # Detailed debug
        if isinstance(response, dict) and 'result' in response and response.get('success'):
            total_bnb = 0
            for result in response.get('result', []):
                asset = result.get('fromAsset')
                amount = result.get('amount')
                bnb_value = result.get('transferedTotal', 0)  # Adjusted key based on Binance API
                total_bnb += float(bnb_value) if bnb_value else 0
                print(f"✅ Converted {amount} {asset} → {bnb_value or 'negligible'} BNB")
            print(f"✅ Total BNB received: {total_bnb:.6f} BNB")
            return True
        else:
            print(f"❌ Dust conversion failed: {response.get('msg', 'Unknown error')}")
            if response.get('code') == -2011:
                print("🔴 Conversion skipped: Balances too low or not eligible")
            # Fallback to spot market
            markets = exchange.load_markets()
            success = True
            for asset, amount in small_balances.items():
                if asset not in ['USDT', 'BNB']:  # Skip USDT and BNB in fallback
                    pair = f"{asset}/BNB"
                    if pair in markets and markets[pair]['spot']:
                        try:
                            if amount > markets[pair].get('limits', {}).get('amount', {}).get('min', 0):
                                order = exchange.create_market_sell_order(pair, amount)
                                print(f"✅ Fallback: Sold {amount:.6f} {asset} for BNB | Order ID: {order['id']}")
                            else:
                                print(f"❌ Fallback skipped: {amount:.6f} {asset} below minimum for {pair}")
                        except Exception as e:
                            print(f"❌ Fallback failed for {asset}: {e}")
                            success = False
                    else:
                        print(f"❌ No spot market for {pair}")
                        success = False
            return success
    except Exception as e:
        print(f"❌ Failed to convert small balances to BNB: {e}")
        return False

def auto_rebalance_wallet(existing_analysis=None, min_score_threshold=15, max_positions=5, enable_trading=False):
    """
    Automatically rebalance wallet based on pattern analysis.
    New logic: Utilizes the full USDT balance for diversification, allocated proportionally based on score.
    """
    print("\n" + "=" * 80)
    print("🤖 AUTO WALLET REBALANCING SYSTEM (v2.0 Proportional Allocation)")
    print("=" * 80)
    if not enable_trading:
        print("⚠️  DEMO MODE - No actual trades will be executed")
        print("⚠️  Set enable_trading=True to execute real trades")

    # Fetch current wallet balances
    print("\n📊 Fetching current wallet balances...")
    balances = get_wallet_balances()
    if not balances:
        print("❌ Could not fetch wallet balances or wallet is empty")
        return

    # Calculate total portfolio value and identify small balances
    total_usdt_value = 0
    small_balances = {}
    usdt_balance = balances.get('USDT', {}).get('total', 0)
    print(f"💰 Found {len(balances)} assets in wallet:")
    for asset, amounts in balances.items():
        amount = amounts['total']
        print(f"   {asset}: {amount:.6f}")
        if asset == 'USDT':
            total_usdt_value += amount
        else:
            try:
                pair = f"{asset}/USDT"
                ticker = exchange.fetch_ticker(pair)
                usdt_value = amount * ticker['last']
                if usdt_value < 0.5:  # Small balance threshold
                    small_balances[asset] = amount
                total_usdt_value += usdt_value
                print(f"      ≈ ${usdt_value:.2f} USDT")
            except:
                print(f"      (Could not get USDT value)")

    print(f"\n💎 Total estimated wallet value: ${total_usdt_value:.2f} USDT")
    print(f"💵 Available for trading: {usdt_balance:.2f} USDT")

    # Get market analysis
    if existing_analysis:
        print("\n♻️  Using existing market analysis...")
        top_opportunities = [opp for opp in existing_analysis if opp['pair'].endswith(('/USDT'))]
    else:
        print("\n🔍 Analyzing market opportunities...")
        top_opportunities = get_best_coins(top_n=20)

    # Filter good opportunities
    good_opportunities = [opp for opp in top_opportunities if
                          opp['score'] >= min_score_threshold and
                          opp['pair'].endswith(('/USDT')) and
                          opp['trend'] in ['up', 'neutral'] and
                          opp.get('price_change_24h', 0) > -10]

    print(f"\n✨ Found {len(good_opportunities)} good opportunities (score ≥ {min_score_threshold}%):")
    for i, opp in enumerate(good_opportunities[:max_positions], 1):
        trend_emoji = "📈" if opp['trend'] == 'up' else "➡️"
        change_emoji = "🟢" if opp.get('price_change_24h', 0) > 0 else "🔴"
        print(
            f"   {i}. {opp['pair']} - Score: {opp['score']:.1f}% {trend_emoji} | 24h: {opp.get('price_change_24h', 0):+.2f}% {change_emoji}")

    # Identify assets to keep vs. convert
    top_assets = {opp['pair'].split('/')[0] for opp in good_opportunities[:max_positions]}
    assets_to_keep = {asset for asset in balances if asset in top_assets and asset != 'USDT'}
    assets_to_convert = {asset for asset in balances if
                         asset not in top_assets and asset not in ['USDT', 'BNB'] and asset not in small_balances}

    print(f"\n🎯 Assets to keep: {', '.join(assets_to_keep) if assets_to_keep else 'None'}")
    print(f"🔄 Assets to convert to USDT: {', '.join(assets_to_convert) if assets_to_convert else 'None'}")
    print(f"🧹 Small balances to convert to BNB: {', '.join(small_balances.keys()) if small_balances else 'None'}")

    # Strategy decision
    strategy = "diversify" if good_opportunities else "convert_to_usdt"
    print(f"\n{'🎯' if strategy == 'diversify' else '🔄'} STRATEGY: {strategy.replace('_', ' ').title()}")

    if not enable_trading:
        print(f"\n🎭 SIMULATION MODE - Here's what would happen:")

    # --- ACTION PHASE ---

    # 1. Convert assets that are no longer top opportunities
    if assets_to_convert:
        print("\n💰 Converting non-top assets to USDT...")
        for asset in assets_to_convert:
            amount_to_convert = balances[asset]['total']
            if enable_trading:
                if convert_to_usdt(asset, amount_to_convert):
                    # Fictional update of USDT balance for subsequent steps
                    usdt_balance += amount_to_convert * exchange.fetch_ticker(f'{asset}/USDT')['last']
            else:
                print(f"   Would convert: {amount_to_convert:.6f} {asset} → USDT")

    # 2. Handle small balances
    if small_balances:
        print("\n🧹 Converting small balances (<$0.5) to BNB...")
        if enable_trading:
            convert_small_balances_to_bnb(small_balances)
        else:
            for asset, amount in small_balances.items():
                print(f"   Would convert: {amount:.6f} {asset} → BNB")

    # 3. Execute main strategy
    if strategy == "diversify":
        # --- NEW PROPORTIONAL ALLOCATION LOGIC ---
        if usdt_balance > 10:  # Minimum USDT to start diversifying
            print(f"\n🎯 Diversifying {usdt_balance:.2f} USDT proportionally among top {max_positions} opportunities...")

            # Select assets to invest in
            assets_to_buy = good_opportunities[:max_positions]
            
            # Calculate the total score of the selected assets
            total_score = sum(opp['score'] for opp in assets_to_buy)
            
            if total_score > 0:
                usdt_to_allocate = usdt_balance
                # Allocate USDT based on the score of each asset
                for opp in assets_to_buy:
                    proportion = opp['score'] / total_score
                    usdt_amount_for_this_asset = usdt_to_allocate * proportion
                    
                    print(f"   - Allocating to {opp['pair']}: Score {opp['score']:.1f} ({proportion:.1%}) -> ${usdt_amount_for_this_asset:.2f} USDT")
                    
                    if enable_trading:
                        buy_asset_with_usdt(opp['pair'], usdt_amount_for_this_asset)
                    else:
                        print(f"     (Simulation: Would buy {opp['pair']} with ${usdt_amount_for_this_asset:.2f})")
            else:
                print("🟡 No score found in opportunities, cannot allocate proportionally.")
        else:
            print("🟡 USDT balance is below $10, skipping diversification.")

    elif strategy == "convert_to_usdt":
        print("\nHolding USDT as no strong opportunities were found.")
        # The conversion of non-top assets was already handled above.

    print(f"\n{'=' * 60}")
    print("📋 REBALANCING SUMMARY")
    print("=" * 60)
    print(f"💎 Final Estimated Portfolio Value: ${total_usdt_value:.2f}")
    print(f"🎯 Strategy Executed: {strategy.replace('_', ' ').title()}")
    if not enable_trading:
        print("\n⚠️  To execute real trades, set enable_trading=True in the main block")
    else:
        print("\n✅ Rebalancing complete!")
    print("=" * 60)


if __name__ == "__main__":
    if not exchange.apiKey or exchange.apiKey == os.environ['API']:
        print("⚠️  Please set your Binance API credentials in GitHub Secrets")
        print("⚠️  The script will try to run with public endpoints only")
    try:
        analyze_btc_detailed()
        print(f"\n{'=' * 70}")
        print("🔎 SCANNING USDT SPOT PAIRS FOR OPPORTUNITIES...")
        print("=" * 70)
        top_coins = get_best_coins(top_n=15)
        print_analysis_results(top_coins)
        get_market_summary(top_coins)
        print(f"\n{'=' * 70}")
        print("⚡ FULL MARKET ANALYSIS COMPLETE - TRADE RESPONSIBLY!")
        print("💡 Tip: Focus on high-scoring pairs with strong patterns")
        print("=" * 70)
        print(f"\n{'=' * 70}")
        print("🤖 AUTOMATIC WALLET REBALANCING")
        print("=" * 70)
        auto_rebalance_wallet(existing_analysis=top_coins, min_score_threshold=15, max_positions=3, enable_trading=True)
        print(f"\n{'=' * 70}")
        print("💡 TO ENABLE REAL TRADING:")
        print("💡 Set enable_trading=True in the auto_rebalance_wallet() call")
        print("💡 ALWAYS test with small amounts first!")
        print("=" * 70)
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure you have ccxt installed: pip install ccxt")
