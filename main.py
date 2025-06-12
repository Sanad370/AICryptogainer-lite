import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Initialize Binance
exchange = ccxt.binance({
    'apiKey': API,  # Replace with your actual API key
    'secret': SECRET,  # Replace with your actual secret
    'sandbox': False,  # Set to True for testnet
    'enableRateLimit': True,
})


# Candlestick Pattern Detection Functions
def detect_hammer(ohlc):
    """Detect Hammer pattern"""
    body = abs(ohlc['close'] - ohlc['open'])
    total_range = ohlc['high'] - ohlc['low']
    if total_range == 0:
        return 0.0

    wick_lower = min(ohlc['open'], ohlc['close']) - ohlc['low']
    wick_upper = ohlc['high'] - max(ohlc['open'], ohlc['close'])

    # Hammer: long lower wick, small body, small upper wick
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

    # Inverted Hammer: long upper wick, small body, small lower wick
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

    # Doji: very small body relative to total range
    return 0.7 if body < total_range * 0.1 else 0.0


def detect_bullish_engulfing(ohlc_prev, ohlc_curr):
    """Detect Bullish Engulfing pattern"""
    prev_bearish = ohlc_prev['close'] < ohlc_prev['open']
    curr_bullish = ohlc_curr['close'] > ohlc_curr['open']

    if prev_bearish and curr_bullish:
        # Current candle engulfs previous candle
        engulfs = (ohlc_curr['open'] < ohlc_prev['close'] and
                   ohlc_curr['close'] > ohlc_prev['open'])
        return 0.9 if engulfs else 0.0
    return 0.0


def detect_bearish_engulfing(ohlc_prev, ohlc_curr):
    """Detect Bearish Engulfing pattern"""
    prev_bullish = ohlc_prev['close'] > ohlc_prev['open']
    curr_bearish = ohlc_curr['close'] < ohlc_curr['open']

    if prev_bullish and curr_bearish:
        # Current candle engulfs previous candle
        engulfs = (ohlc_curr['open'] > ohlc_prev['close'] and
                   ohlc_curr['close'] < ohlc_prev['open'])
        return 0.9 if engulfs else 0.0
    return 0.0


def detect_morning_star(ohlc_list):
    """Detect Morning Star pattern (3 candles)"""
    if len(ohlc_list) < 3:
        return 0.0

    first, second, third = ohlc_list[-3], ohlc_list[-2], ohlc_list[-1]

    # First: bearish candle
    first_bearish = first['close'] < first['open']
    # Second: small body (doji-like)
    second_small_body = abs(second['close'] - second['open']) < (second['high'] - second['low']) * 0.3
    # Third: bullish candle that closes above first candle's midpoint
    third_bullish = third['close'] > third['open']
    third_recovery = third['close'] > (first['open'] + first['close']) / 2

    return 0.95 if (first_bearish and second_small_body and third_bullish and third_recovery) else 0.0


def detect_evening_star(ohlc_list):
    """Detect Evening Star pattern (3 candles)"""
    if len(ohlc_list) < 3:
        return 0.0

    first, second, third = ohlc_list[-3], ohlc_list[-2], ohlc_list[-1]

    # First: bullish candle
    first_bullish = first['close'] > first['open']
    # Second: small body (doji-like)
    second_small_body = abs(second['close'] - second['open']) < (second['high'] - second['low']) * 0.3
    # Third: bearish candle that closes below first candle's midpoint
    third_bearish = third['close'] < third['open']
    third_decline = third['close'] < (first['open'] + first['close']) / 2

    return 0.95 if (first_bullish and second_small_body and third_bearish and third_decline) else 0.0


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
    """Calculate aggregate pattern score"""
    if len(ohlc_data) < 3:
        return 0.0

    score = 0.0
    trend = detect_trend(ohlc_data)

    # Current candle patterns
    current = ohlc_data[-1]
    score += detect_hammer(current)
    score += detect_inverted_hammer(current)
    score += detect_doji(current)

    # Trend-specific patterns
    if trend == 'up':
        score += detect_hanging_man(current, 'up') * 0.5  # Bearish in uptrend
        score += detect_shooting_star(current, 'up') * 0.5  # Bearish in uptrend
    elif trend == 'down':
        score += detect_hammer(current) * 1.2  # More bullish in downtrend
        score += detect_inverted_hammer(current) * 1.2  # More bullish in downtrend

    # Two-candle patterns
    if len(ohlc_data) >= 2:
        prev, curr = ohlc_data[-2], ohlc_data[-1]
        score += detect_bullish_engulfing(prev, curr)
        score += detect_bearish_engulfing(prev, curr) * 0.5  # Weight bearish less for "invest now"

    # Three-candle patterns
    if len(ohlc_data) >= 3:
        score += detect_morning_star(ohlc_data)
        score += detect_evening_star(ohlc_data) * 0.3  # Weight bearish less

    # Normalize score (0-100%)
    return min(100.0, max(0.0, score * 25))  # Scale factor


def analyze_single_pair(pair, limit=6):
    """Analyze a single trading pair with improved error handling"""
    try:
        # Fetch OHLCV data
        ohlcv = exchange.fetch_ohlcv(pair, timeframe='4h', limit=limit)
        if len(ohlcv) < 3:
            return None

        # Convert to list of dictionaries
        ohlc_data = []
        for candle in ohlcv:
            ohlc_data.append({
                'timestamp': candle[0],
                'open': float(candle[1]),
                'high': float(candle[2]),
                'low': float(candle[3]),
                'close': float(candle[4]),
                'volume': float(candle[5])
            })

        # Calculate pattern score
        score = calculate_pattern_score(ohlc_data)
        trend = detect_trend(ohlc_data)

        # Get current price info
        current_price = ohlc_data[-1]['close']
        volume_24h = sum([c['volume'] for c in ohlc_data[-6:]])  # Approximate 24h volume

        # Calculate price change percentage
        price_change_24h = ((ohlc_data[-1]['close'] - ohlc_data[0]['close']) / ohlc_data[0]['close']) * 100

        return {
            'pair': pair,
            'score': score,
            'trend': trend,
            'current_price': current_price,
            'volume_24h': volume_24h,
            'price_change_24h': price_change_24h,
            'last_updated': datetime.now()
        }

    except ccxt.NetworkError as e:
        print(f"Network error for {pair}: {e}")
        return None
    except ccxt.ExchangeError as e:
        print(f"Exchange error for {pair}: {e}")
        return None
    except Exception as e:
        # Silently handle other errors to avoid spam
        return None


def get_best_coins(top_n=10, include_all_pairs=True):
    """Get best coins based on candlestick pattern analysis from ALL available pairs"""
    print("Loading markets...")
    markets = exchange.load_markets()

    # Get ALL spot trading pairs (USDT, BTC, ETH, BNB pairs)
    if include_all_pairs:
        # Include all major quote currencies
        spot_pairs = []
        for pair in markets:
            if markets[pair]['spot'] and markets[pair]['active']:
                # Include USDT, BTC, ETH, BNB pairs
                if any(pair.endswith(f'/{quote}') for quote in ['USDT', 'BTC', 'ETH', 'BNB']):
                    spot_pairs.append(pair)
    else:
        # Only USDT pairs (more liquid and easier to trade)
        spot_pairs = [pair for pair in markets if
                      pair.endswith('/USDT') and markets[pair]['spot'] and markets[pair]['active']]

    # Remove stablecoins and problematic pairs
    excluded = ['USDT/USDT', 'BUSD/USDT', 'TUSD/USDT', 'USDC/USDT', 'DAI/USDT', 'FDUSD/USDT']
    spot_pairs = [pair for pair in spot_pairs if pair not in excluded]

    print(f"Found {len(spot_pairs)} active spot trading pairs")
    print(f"Analyzing ALL {len(spot_pairs)} pairs for patterns...")
    print("This may take a few minutes - please wait...")

    results = []
    failed_pairs = []

    for i, pair in enumerate(spot_pairs):
        # Progress indicator every 50 pairs
        if i % 50 == 0:
            print(f"Progress: {i}/{len(spot_pairs)} pairs analyzed ({(i / len(spot_pairs) * 100):.1f}%)")

        result = analyze_single_pair(pair)
        if result and result['score'] > 0:
            results.append(result)
        elif result is None:
            failed_pairs.append(pair)

    print(f"\n✅ Analysis Complete!")
    print(f"📊 Successfully analyzed: {len(results)} pairs")
    print(f"❌ Failed to analyze: {len(failed_pairs)} pairs")
    print(f"🎯 Pairs with positive signals: {len([r for r in results if r['score'] > 20])}")

    # Sort by score
    results.sort(key=lambda x: x['score'], reverse=True)

    return results[:top_n]


def print_analysis_results(results):
    """Print formatted analysis results"""
    print("\n" + "=" * 90)
    print("🚀 TOP CRYPTO INVESTMENT OPPORTUNITIES (Next 4 Hours) - ALL BINANCE PAIRS")
    print("=" * 90)

    if not results:
        print("No significant patterns detected in analyzed pairs.")
        return

    for i, result in enumerate(results, 1):
        trend_emoji = "📈" if result['trend'] == 'up' else "📉" if result['trend'] == 'down' else "➡️"

        # Format price based on pair type
        if result['pair'].endswith('/USDT'):
            price_format = f"${result['current_price']:,.4f}"
        elif result['pair'].endswith('/BTC'):
            price_format = f"{result['current_price']:.8f} BTC"
        elif result['pair'].endswith('/ETH'):
            price_format = f"{result['current_price']:.8f} ETH"
        else:
            price_format = f"{result['current_price']:.8f}"

        # Color coding for price change
        change_emoji = "🟢" if result.get('price_change_24h', 0) > 0 else "🔴" if result.get('price_change_24h',
                                                                                           0) < 0 else "⚪"

        print(f"\n{i}. {result['pair']} {trend_emoji}")
        print(f"   📊 Pattern Score: {result['score']:.1f}% 🎯")
        print(f"   💰 Current Price: {price_format}")
        print(f"   📈 24h Change: {result.get('price_change_24h', 0):+.2f}% {change_emoji}")
        print(f"   🔄 Trend: {result['trend'].upper()}")
        print(f"   📦 24h Volume: {result['volume_24h']:,.2f}")
        print(f"   ⏰ Analysis Time: {result['last_updated'].strftime('%Y-%m-%d %H:%M:%S')}")


def get_market_summary(results):
    """Print market summary statistics"""
    if not results:
        return

    print(f"\n{'=' * 60}")
    print("📋 MARKET ANALYSIS SUMMARY")
    print("=" * 60)

    # Count by quote currency
    usdt_pairs = len([r for r in results if r['pair'].endswith('/USDT')])
    btc_pairs = len([r for r in results if r['pair'].endswith('/BTC')])
    eth_pairs = len([r for r in results if r['pair'].endswith('/ETH')])
    bnb_pairs = len([r for r in results if r['pair'].endswith('/BNB')])

    print(f"💲 USDT Pairs in Top: {usdt_pairs}")
    print(f"₿ BTC Pairs in Top: {btc_pairs}")
    print(f"⧫ ETH Pairs in Top: {eth_pairs}")
    print(f"🟡 BNB Pairs in Top: {bnb_pairs}")

    # Trend analysis
    uptrend = len([r for r in results if r['trend'] == 'up'])
    downtrend = len([r for r in results if r['trend'] == 'down'])
    neutral = len([r for r in results if r['trend'] == 'neutral'])

    print(f"\n📊 TREND DISTRIBUTION:")
    print(f"📈 Uptrend: {uptrend}")
    print(f"📉 Downtrend: {downtrend}")
    print(f"➡️ Neutral: {neutral}")

    # Score distribution
    avg_score = sum([r['score'] for r in results]) / len(results)
    max_score = max([r['score'] for r in results])

    print(f"\n🎯 PATTERN SCORES:")
    print(f"Average Score: {avg_score:.1f}%")
    print(f"Highest Score: {max_score:.1f}%")
    print(f"Strong Signals (>50%): {len([r for r in results if r['score'] > 50])}")
    print(f"Moderate Signals (20-50%): {len([r for r in results if 20 < r['score'] <= 50])}")


def analyze_btc_detailed():
    """Detailed analysis of BTC/USDT"""
    print("\n" + "=" * 60)
    print("🔍 DETAILED BTC/USDT PATTERN ANALYSIS")
    print("=" * 60)

    result = analyze_single_pair('BTC/USDT', limit=10)
    if not result:
        print("Could not analyze BTC/USDT")
        return

    # Get the raw data for detailed analysis
    ohlcv = exchange.fetch_ohlcv('BTC/USDT', timeframe='4h', limit=6)
    ohlc_data = []
    for candle in ohlcv:
        ohlc_data.append({
            'timestamp': datetime.fromtimestamp(candle[0] / 1000),
            'open': candle[1],
            'high': candle[2],
            'low': candle[3],
            'close': candle[4],
            'volume': candle[5]
        })

    print(f"Overall Score: {result['score']:.1f}%")
    print(f"Trend: {result['trend'].upper()}")
    print(f"Current Price: ${result['current_price']:,.2f}")

    # Individual pattern detection
    current = ohlc_data[-1]
    print(f"\n📊 Individual Pattern Scores:")
    print(f"Hammer: {detect_hammer(current):.1f}")
    print(f"Doji: {detect_doji(current):.1f}")
    print(f"Inverted Hammer: {detect_inverted_hammer(current):.1f}")

    if len(ohlc_data) >= 2:
        prev, curr = ohlc_data[-2], ohlc_data[-1]
        print(f"Bullish Engulfing: {detect_bullish_engulfing(prev, curr):.1f}")
        print(f"Bearish Engulfing: {detect_bearish_engulfing(prev, curr):.1f}")

    if len(ohlc_data) >= 3:
        print(f"Morning Star: {detect_morning_star(ohlc_data):.1f}")
        print(f"Evening Star: {detect_evening_star(ohlc_data):.1f}")


def get_wallet_balances():
    """Get all non-zero balances in spot wallet"""
    try:
        balance = exchange.fetch_balance()
        non_zero_balances = {}

        for asset, amounts in balance.items():
            if asset not in ['info', 'free', 'used', 'total'] and amounts.get('total', 0) > 0:
                non_zero_balances[asset] = amounts

        return non_zero_balances
    except Exception as e:
        print(f"Error fetching wallet balance: {e}")
        return {}


def convert_to_usdt(asset, amount):
    """Convert an asset to USDT"""
    try:
        pair = f"{asset}/USDT"
        markets = exchange.load_markets()

        if pair not in markets:
            print(f"❌ No USDT pair available for {asset}")
            return False

        # Check minimum order size
        market = markets[pair]
        min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)

        if amount < min_amount:
            print(f"❌ Amount {amount} {asset} below minimum {min_amount}")
            return False

        # Place market sell order
        order = exchange.create_market_sell_order(pair, amount)
        print(f"✅ Sold {amount} {asset} → USDT | Order ID: {order['id']}")
        return True

    except Exception as e:
        print(f"❌ Failed to sell {asset}: {e}")
        return False


def buy_asset_with_usdt(pair, usdt_amount):
    """Buy an asset using USDT"""
    try:
        markets = exchange.load_markets()

        if pair not in markets:
            print(f"❌ Pair {pair} not available")
            return False

        market = markets[pair]
        min_cost = market.get('limits', {}).get('cost', {}).get('min', 0)

        if usdt_amount < min_cost:
            print(f"❌ Amount ${usdt_amount} below minimum ${min_cost} for {pair}")
            return False

        # Place market buy order
        order = exchange.create_market_buy_order(pair, None, usdt_amount)
        print(f"✅ Bought {pair} with ${usdt_amount} USDT | Order ID: {order['id']}")
        return True

    except Exception as e:
        print(f"❌ Failed to buy {pair}: {e}")
        return False


def auto_rebalance_wallet(min_score_threshold=35, max_positions=5, enable_trading=False):
    """
    Automatically rebalance wallet based on pattern analysis

    Parameters:
    - min_score_threshold: Minimum pattern score to consider buying (default 35%)
    - max_positions: Maximum number of different positions to hold (default 5)
    - enable_trading: Set to True to actually execute trades (default False for safety)
    """
    print("\n" + "=" * 80)
    print("🤖 AUTO WALLET REBALANCING SYSTEM")
    print("=" * 80)

    if not enable_trading:
        print("⚠️  DEMO MODE - No actual trades will be executed")
        print("⚠️  Set enable_trading=True to execute real trades")

    # Get current wallet balances
    print("\n📊 Fetching current wallet balances...")
    balances = get_wallet_balances()

    if not balances:
        print("❌ Could not fetch wallet balances or wallet is empty")
        return

    print(f"💰 Found {len(balances)} assets in wallet:")
    total_usdt_value = 0

    for asset, amounts in balances.items():
        amount = amounts['total']
        print(f"   {asset}: {amount:.6f}")

        # Estimate USDT value (rough calculation)
        if asset == 'USDT':
            total_usdt_value += amount
        else:
            # Try to get current price in USDT
            try:
                pair = f"{asset}/USDT"
                ticker = exchange.fetch_ticker(pair)
                usdt_value = amount * ticker['last']
                total_usdt_value += usdt_value
                print(f"      ≈ ${usdt_value:.2f} USDT")
            except:
                print(f"      (Could not get USDT value)")

    print(f"\n💎 Total estimated wallet value: ${total_usdt_value:.2f} USDT")

    # Get top opportunities
    print("\n🔍 Analyzing market opportunities...")
    top_opportunities = get_best_coins(top_n=20, include_all_pairs=False)  # Only USDT pairs for easier trading

    # Filter opportunities by score and other criteria
    good_opportunities = []
    for opp in top_opportunities:
        if (opp['score'] >= min_score_threshold and
                opp['pair'].endswith('/USDT') and
                opp['trend'] in ['up', 'neutral'] and
                opp.get('price_change_24h', 0) > -10):  # Not crashing
            good_opportunities.append(opp)

    print(f"\n✨ Found {len(good_opportunities)} good opportunities (score ≥ {min_score_threshold}%):")
    for i, opp in enumerate(good_opportunities[:max_positions], 1):
        trend_emoji = "📈" if opp['trend'] == 'up' else "➡️"
        change_emoji = "🟢" if opp.get('price_change_24h', 0) > 0 else "🔴"
        print(
            f"   {i}. {opp['pair']} - Score: {opp['score']:.1f}% {trend_emoji} | 24h: {opp.get('price_change_24h', 0):+.2f}% {change_emoji}")

    # Decide strategy
    if len(good_opportunities) == 0:
        print(f"\n❌ No opportunities meet criteria (score ≥ {min_score_threshold}%)")
        print("🔄 STRATEGY: Convert everything to USDT and wait for better opportunities")
        strategy = "convert_to_usdt"
    else:
        print(f"\n✅ Found {len(good_opportunities)} good opportunities")
        print("🎯 STRATEGY: Diversify into top opportunities")
        strategy = "diversify"

    # Execute strategy
    if not enable_trading:
        print(f"\n🎭 SIMULATION MODE - Here's what would happen:")

    if strategy == "convert_to_usdt":
        print("\n💰 Converting all assets to USDT...")
        for asset, amounts in balances.items():
            if asset != 'USDT' and amounts['total'] > 0:
                amount = amounts['total']
                if enable_trading:
                    convert_to_usdt(asset, amount)
                else:
                    print(f"   Would sell: {amount:.6f} {asset} → USDT")

    elif strategy == "diversify":
        # First convert everything to USDT
        print("\n🔄 Step 1: Converting all assets to USDT...")
        usdt_balance = balances.get('USDT', {}).get('total', 0)

        for asset, amounts in balances.items():
            if asset != 'USDT' and amounts['total'] > 0:
                amount = amounts['total']
                if enable_trading:
                    if convert_to_usdt(asset, amount):
                        # Rough estimate of USDT gained
                        try:
                            ticker = exchange.fetch_ticker(f"{asset}/USDT")
                            usdt_balance += amount * ticker['last']
                        except:
                            pass
                else:
                    print(f"   Would sell: {amount:.6f} {asset} → USDT")

        # Then diversify into top opportunities
        print(f"\n🎯 Step 2: Diversifying into {min(len(good_opportunities), max_positions)} positions...")
        positions_to_buy = good_opportunities[:max_positions]
        allocation_per_position = total_usdt_value / len(positions_to_buy)

        for opp in positions_to_buy:
            pair = opp['pair']
            if enable_trading:
                buy_asset_with_usdt(pair, allocation_per_position)
            else:
                asset = pair.split('/')[0]
                print(f"   Would buy: {asset} with ${allocation_per_position:.2f} USDT")

    # Summary
    print(f"\n{'=' * 60}")
    print("📋 REBALANCING SUMMARY")
    print("=" * 60)
    print(f"💎 Total Portfolio Value: ${total_usdt_value:.2f}")
    print(f"🎯 Strategy: {strategy.replace('_', ' ').title()}")
    print(f"📊 Opportunities Found: {len(good_opportunities)}")
    print(f"⚙️  Score Threshold: {min_score_threshold}%")
    print(f"📈 Max Positions: {max_positions}")

    if strategy == "diversify":
        print(f"💰 Allocation per position: ${allocation_per_position:.2f}")
        print("🔥 Selected opportunities:")
        for i, opp in enumerate(positions_to_buy, 1):
            print(f"   {i}. {opp['pair']} (Score: {opp['score']:.1f}%)")

    if not enable_trading:
        print("\n⚠️  To execute real trades, call:")
        print("   auto_rebalance_wallet(enable_trading=True)")
    else:
        print("\n✅ Rebalancing complete!")

    print("=" * 60)




def get_wallet_balances():
    """Get all non-zero balances in spot wallet"""
    try:
        balance = exchange.fetch_balance()
        non_zero_balances = {}

        # Debug: Print the structure to understand the response
        print(f"Balance response type: {type(balance)}")
        print(f"Balance keys: {list(balance.keys()) if isinstance(balance, dict) else 'Not a dict'}")

        # Handle different response structures
        if isinstance(balance, dict):
            for asset, amounts in balance.items():
                # Skip metadata fields
                if asset in ['info', 'free', 'used', 'total', 'datetime', 'timestamp']:
                    continue

                # Handle case where amounts might be a dict or a number
                if isinstance(amounts, dict):
                    total_amount = amounts.get('total', 0)
                elif isinstance(amounts, (int, float)):
                    total_amount = amounts
                else:
                    continue

                # Only include assets with positive balance
                if total_amount > 0:
                    if isinstance(amounts, dict):
                        non_zero_balances[asset] = amounts
                    else:
                        # Create dict structure if amounts is just a number
                        non_zero_balances[asset] = {
                            'total': total_amount,
                            'free': total_amount,
                            'used': 0
                        }

        return non_zero_balances

    except Exception as e:
        print(f"Error fetching wallet balance: {e}")
        print(f"Error type: {type(e)}")

        # Try alternative method - get account info directly
        try:
            print("Trying alternative balance method...")
            account = exchange.fetch_account()
            print(f"Account info keys: {list(account.keys()) if isinstance(account, dict) else 'Not a dict'}")

            if 'balances' in account:
                balances = account['balances']
                non_zero_balances = {}

                for balance_item in balances:
                    asset = balance_item.get('asset')
                    free = float(balance_item.get('free', 0))
                    locked = float(balance_item.get('locked', 0))
                    total = free + locked

                    if total > 0:
                        non_zero_balances[asset] = {
                            'total': total,
                            'free': free,
                            'used': locked
                        }

                return non_zero_balances

        except Exception as e2:
            print(f"Alternative method also failed: {e2}")

        return {}


def convert_to_usdt(asset, amount):
    """Convert an asset to USDT"""
    try:
        pair = f"{asset}/USDT"
        markets = exchange.load_markets()

        if pair not in markets:
            print(f"❌ No USDT pair available for {asset}")
            return False

        # Check minimum order size
        market = markets[pair]
        min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)

        if amount < min_amount:
            print(f"❌ Amount {amount} {asset} below minimum {min_amount}")
            return False

        # Place market sell order
        order = exchange.create_market_sell_order(pair, amount)
        print(f"✅ Sold {amount} {asset} → USDT | Order ID: {order['id']}")
        return True

    except Exception as e:
        print(f"❌ Failed to sell {asset}: {e}")
        return False


def buy_asset_with_usdt(pair, usdt_amount):
    """Buy an asset using USDT"""
    try:
        markets = exchange.load_markets()

        if pair not in markets:
            print(f"❌ Pair {pair} not available")
            return False

        market = markets[pair]
        min_cost = market.get('limits', {}).get('cost', {}).get('min', 0)

        if usdt_amount < min_cost:
            print(f"❌ Amount ${usdt_amount} below minimum ${min_cost} for {pair}")
            return False

        # Place market buy order
        order = exchange.create_market_buy_order(pair, None, usdt_amount)
        print(f"✅ Bought {pair} with ${usdt_amount} USDT | Order ID: {order['id']}")
        return True

    except Exception as e:
        print(f"❌ Failed to buy {pair}: {e}")
        return False


def auto_rebalance_wallet(existing_analysis=None, min_score_threshold=35, max_positions=5, enable_trading=False):
    """
    Automatically rebalance wallet based on pattern analysis

    Parameters:
    - existing_analysis: Use existing market analysis results to avoid double scanning
    - min_score_threshold: Minimum pattern score to consider buying (default 35%)
    - max_positions: Maximum number of different positions to hold (default 5)
    - enable_trading: Set to True to actually execute trades (default False for safety)
    """
    print("\n" + "=" * 80)
    print("🤖 AUTO WALLET REBALANCING SYSTEM")
    print("=" * 80)

    if not enable_trading:
        print("⚠️  DEMO MODE - No actual trades will be executed")
        print("⚠️  Set enable_trading=True to execute real trades")

    # Get current wallet balances
    print("\n📊 Fetching current wallet balances...")
    balances = get_wallet_balances()

    if not balances:
        print("❌ Could not fetch wallet balances or wallet is empty")
        return

    print(f"💰 Found {len(balances)} assets in wallet:")
    total_usdt_value = 0

    for asset, amounts in balances.items():
        amount = amounts['total']
        print(f"   {asset}: {amount:.6f}")

        # Estimate USDT value (rough calculation)
        if asset == 'USDT':
            total_usdt_value += amount
        else:
            # Try to get current price in USDT
            try:
                pair = f"{asset}/USDT"
                ticker = exchange.fetch_ticker(pair)
                usdt_value = amount * ticker['last']
                total_usdt_value += usdt_value
                print(f"      ≈ ${usdt_value:.2f} USDT")
            except:
                print(f"      (Could not get USDT value)")

    print(f"\n💎 Total estimated wallet value: ${total_usdt_value:.2f} USDT")

    # Use existing analysis or get new opportunities
    if existing_analysis:
        print("\n♻️  Using existing market analysis (no double scanning)...")
        # Filter existing analysis for USDT pairs only
        top_opportunities = [opp for opp in existing_analysis if opp['pair'].endswith('/USDT')]
    else:
        print("\n🔍 Analyzing market opportunities...")
        top_opportunities = get_best_coins(top_n=20, include_all_pairs=False)  # Only USDT pairs for easier trading

    # Filter opportunities by score and other criteria
    good_opportunities = []
    for opp in top_opportunities:
        if (opp['score'] >= min_score_threshold and
                opp['pair'].endswith('/USDT') and
                opp['trend'] in ['up', 'neutral'] and
                opp.get('price_change_24h', 0) > -10):  # Not crashing
            good_opportunities.append(opp)

    print(f"\n✨ Found {len(good_opportunities)} good opportunities (score ≥ {min_score_threshold}%):")
    for i, opp in enumerate(good_opportunities[:max_positions], 1):
        trend_emoji = "📈" if opp['trend'] == 'up' else "➡️"
        change_emoji = "🟢" if opp.get('price_change_24h', 0) > 0 else "🔴"
        print(
            f"   {i}. {opp['pair']} - Score: {opp['score']:.1f}% {trend_emoji} | 24h: {opp.get('price_change_24h', 0):+.2f}% {change_emoji}")

    # Decide strategy
    if len(good_opportunities) == 0:
        print(f"\n❌ No opportunities meet criteria (score ≥ {min_score_threshold}%)")
        print("🔄 STRATEGY: Convert everything to USDT and wait for better opportunities")
        strategy = "convert_to_usdt"
    else:
        print(f"\n✅ Found {len(good_opportunities)} good opportunities")
        print("🎯 STRATEGY: Diversify into top opportunities")
        strategy = "diversify"

    # Execute strategy
    if not enable_trading:
        print(f"\n🎭 SIMULATION MODE - Here's what would happen:")

    if strategy == "convert_to_usdt":
        print("\n💰 Converting all assets to USDT...")
        for asset, amounts in balances.items():
            if asset != 'USDT' and amounts['total'] > 0:
                amount = amounts['total']
                if enable_trading:
                    convert_to_usdt(asset, amount)
                else:
                    print(f"   Would sell: {amount:.6f} {asset} → USDT")

    elif strategy == "diversify":
        # First convert everything to USDT
        print("\n🔄 Step 1: Converting all assets to USDT...")
        usdt_balance = balances.get('USDT', {}).get('total', 0)

        for asset, amounts in balances.items():
            if asset != 'USDT' and amounts['total'] > 0:
                amount = amounts['total']
                if enable_trading:
                    if convert_to_usdt(asset, amount):
                        # Rough estimate of USDT gained
                        try:
                            ticker = exchange.fetch_ticker(f"{asset}/USDT")
                            usdt_balance += amount * ticker['last']
                        except:
                            pass
                else:
                    print(f"   Would sell: {amount:.6f} {asset} → USDT")

        # Then diversify into top opportunities
        print(f"\n🎯 Step 2: Diversifying into {min(len(good_opportunities), max_positions)} positions...")
        positions_to_buy = good_opportunities[:max_positions]
        allocation_per_position = total_usdt_value / len(positions_to_buy)

        for opp in positions_to_buy:
            pair = opp['pair']
            if enable_trading:
                buy_asset_with_usdt(pair, allocation_per_position)
            else:
                asset = pair.split('/')[0]
                print(f"   Would buy: {asset} with ${allocation_per_position:.2f} USDT")

    # Summary
    print(f"\n{'=' * 60}")
    print("📋 REBALANCING SUMMARY")
    print("=" * 60)
    print(f"💎 Total Portfolio Value: ${total_usdt_value:.2f}")
    print(f"🎯 Strategy: {strategy.replace('_', ' ').title()}")
    print(f"📊 Opportunities Found: {len(good_opportunities)}")
    print(f"⚙️  Score Threshold: {min_score_threshold}%")
    print(f"📈 Max Positions: {max_positions}")

    if strategy == "diversify":
        print(f"💰 Allocation per position: ${allocation_per_position:.2f}")
        print("🔥 Selected opportunities:")
        for i, opp in enumerate(positions_to_buy, 1):
            print(f"   {i}. {opp['pair']} (Score: {opp['score']:.1f}%)")

    if not enable_trading:
        print("\n⚠️  To execute real trades, call:")
        print("   auto_rebalance_wallet(enable_trading=True)")
    else:
        print("\n✅ Rebalancing complete!")

    print("=" * 60)


if __name__ == "__main__":
    # Check if API keys are set
    if exchange.apiKey == API:
        print("⚠️  Please set your Binance API credentials in the code")
        print("⚠️  The script will try to run with public endpoints only")

    try:
        # First, do detailed BTC analysis
        analyze_btc_detailed()

        # Then find top opportunities from ALL pairs
        print(f"\n{'=' * 70}")
        print("🔎 SCANNING ALL BINANCE SPOT PAIRS FOR OPPORTUNITIES...")
        print("=" * 70)

        # Analyze ALL pairs (this will take several minutes)
        top_coins = get_best_coins(top_n=15, include_all_pairs=True)
        print_analysis_results(top_coins)
        get_market_summary(top_coins)

        print(f"\n{'=' * 70}")
        print("⚡ FULL MARKET ANALYSIS COMPLETE - TRADE RESPONSIBLY!")
        print("💡 Tip: Focus on USDT pairs for easier trading")
        print("=" * 70)

        # NEW: Auto-rebalance wallet based on analysis
        print(f"\n{'=' * 70}")
        print("🤖 AUTOMATIC WALLET REBALANCING")
        print("=" * 70)

        # Run in demo mode first (safe) - REUSE existing analysis
        auto_rebalance_wallet(
            existing_analysis=top_coins,  # Pass the existing analysis to avoid double scanning
            min_score_threshold=35,  # Only buy if pattern score ≥ 35%
            max_positions=3,  # Max 3 different positions
            enable_trading=True  # Set to True to actually trade
        )

        print(f"\n{'=' * 70}")
        print("💡 TO ENABLE REAL TRADING:")
        print("💡 Set enable_trading=True in the auto_rebalance_wallet() call")
        print("💡 ALWAYS test with small amounts first!")
        print("=" * 70)

    except Exception as e:
        print(f"Error: {e}")
        print("Make sure you have ccxt installed: pip install ccxt")
