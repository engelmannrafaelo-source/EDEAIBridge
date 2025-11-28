#!/bin/bash

# Analyze Request Duration Statistics - Tool-Aware Version
# Separates analysis for tool vs non-tool requests
# Usage: ./scripts/analyze_thresholds_v2.sh

cd "$(dirname "$0")/.."

LOG_FILE="logs/app.log"

if [ ! -f "$LOG_FILE" ]; then
    echo "❌ Log file not found: $LOG_FILE"
    exit 1
fi

echo "🔍 Analyzing request durations (Tool-Aware Analysis)..."
echo ""

# Extract durations - split by tool usage
DURATIONS_NO_TOOLS=$(grep "EVENT:" "$LOG_FILE" | \
  grep "chat_completion" | \
  jq -r 'select(.data.tools_enabled == false or .data.tools_enabled == null) | .data.duration_seconds' 2>/dev/null | \
  grep -v null)

DURATIONS_WITH_TOOLS=$(grep "EVENT:" "$LOG_FILE" | \
  grep "chat_completion" | \
  jq -r 'select(.data.tools_enabled == true) | .data.duration_seconds' 2>/dev/null | \
  grep -v null)

# Count samples
COUNT_NO_TOOLS=$(echo "$DURATIONS_NO_TOOLS" | wc -l | tr -d ' ')
COUNT_WITH_TOOLS=$(echo "$DURATIONS_WITH_TOOLS" | wc -l | tr -d ' ')

if [ "$COUNT_NO_TOOLS" -eq 0 ] && [ "$COUNT_WITH_TOOLS" -eq 0 ]; then
    echo "❌ No request duration data found."
    exit 1
fi

echo "📊 Sample Distribution:"
echo "  Non-tool requests: $COUNT_NO_TOOLS"
echo "  Tool requests:     $COUNT_WITH_TOOLS"
echo ""

# Analyze with Python
python3 << EOF
import sys
import statistics

def analyze_durations(durations_str, label):
    """Analyze duration statistics for a set of requests."""
    durations = [float(d) for d in durations_str.strip().split('\n') if d]

    if len(durations) == 0:
        print(f"\n⚠️  No {label} data available")
        return None

    avg = statistics.mean(durations)
    median = statistics.median(durations)
    min_dur = min(durations)
    max_dur = max(durations)

    if len(durations) >= 2:
        stdev = statistics.stdev(durations)
    else:
        stdev = 0

    sorted_durs = sorted(durations)
    p90 = sorted_durs[int(len(durations) * 0.90)]
    p95 = sorted_durs[int(len(durations) * 0.95)]

    print(f"\n{'=' * 60}")
    print(f"📊 {label}")
    print(f"{'=' * 60}")
    print(f"Sample Size:    {len(durations)} requests")
    print(f"")
    print(f"Central Tendency:")
    print(f"  Average:      {avg:.2f}s")
    print(f"  Median:       {median:.2f}s")
    print(f"")
    print(f"Spread:")
    print(f"  Std Dev:      {stdev:.2f}s")
    print(f"  Min:          {min_dur:.2f}s")
    print(f"  Max:          {max_dur:.2f}s")
    print(f"  P90:          {p90:.2f}s")
    print(f"  P95:          {p95:.2f}s")

    # Calculate thresholds
    if stdev > 0:
        slow_statistical = avg + stdev
        very_slow_statistical = avg + (2 * stdev)
    else:
        slow_statistical = avg * 1.5
        very_slow_statistical = avg * 2.0

    slow_percentile = p90
    very_slow_percentile = p95

    return {
        'avg': avg,
        'stdev': stdev,
        'p90': p90,
        'p95': p95,
        'slow_statistical': slow_statistical,
        'very_slow_statistical': very_slow_statistical,
        'slow_percentile': slow_percentile,
        'very_slow_percentile': very_slow_percentile,
        'count': len(durations)
    }

# Analyze non-tool requests
no_tools_data = """$DURATIONS_NO_TOOLS"""
no_tools_stats = analyze_durations(no_tools_data, "NON-TOOL REQUESTS (enable_tools=false)")

# Analyze tool requests
with_tools_data = """$DURATIONS_WITH_TOOLS"""
with_tools_stats = analyze_durations(with_tools_data, "TOOL REQUESTS (enable_tools=true)")

# Recommendations
print(f"\n{'=' * 60}")
print(f"💡 RECOMMENDED THRESHOLDS")
print(f"{'=' * 60}")

if no_tools_stats and no_tools_stats['count'] >= 10:
    print(f"\n🔧 NON-TOOL REQUESTS:")
    print(f"  Method 1: Statistical (avg ± σ)")
    print(f"    SLOW_REQUEST_THRESHOLD={no_tools_stats['slow_statistical']:.1f}")
    print(f"    VERY_SLOW_REQUEST_THRESHOLD={no_tools_stats['very_slow_statistical']:.1f}")
    print(f"")
    print(f"  Method 2: Percentile (P90, P95)")
    print(f"    SLOW_REQUEST_THRESHOLD={no_tools_stats['slow_percentile']:.1f}")
    print(f"    VERY_SLOW_REQUEST_THRESHOLD={no_tools_stats['very_slow_percentile']:.1f}")
elif no_tools_stats:
    print(f"\n⚠️  NON-TOOL REQUESTS: Only {no_tools_stats['count']} samples")
    print(f"  Recommendation: Keep defaults (5.0s, 10.0s)")

if with_tools_stats and with_tools_stats['count'] >= 10:
    print(f"\n🛠️  TOOL REQUESTS:")
    print(f"  Method 1: Statistical (avg ± σ)")
    print(f"    SLOW_REQUEST_THRESHOLD_TOOLS={with_tools_stats['slow_statistical']:.1f}")
    print(f"    VERY_SLOW_REQUEST_THRESHOLD_TOOLS={with_tools_stats['very_slow_statistical']:.1f}")
    print(f"")
    print(f"  Method 2: Percentile (P90, P95)")
    print(f"    SLOW_REQUEST_THRESHOLD_TOOLS={with_tools_stats['slow_percentile']:.1f}")
    print(f"    VERY_SLOW_REQUEST_THRESHOLD_TOOLS={with_tools_stats['very_slow_percentile']:.1f}")
elif with_tools_stats:
    print(f"\n⚠️  TOOL REQUESTS: Only {with_tools_stats['count']} samples")
    print(f"  Recommendation: Keep defaults (30.0s, 60.0s)")

# Final recommendations
print(f"\n{'=' * 60}")
print(f"📝 COPY TO .ENV")
print(f"{'=' * 60}")

if no_tools_stats and no_tools_stats['count'] >= 10:
    print(f"\n# Non-tool request thresholds (Method 1 - Statistical)")
    print(f"SLOW_REQUEST_THRESHOLD={no_tools_stats['slow_statistical']:.1f}")
    print(f"VERY_SLOW_REQUEST_THRESHOLD={no_tools_stats['very_slow_statistical']:.1f}")
else:
    print(f"\n# Non-tool request thresholds (Defaults - insufficient data)")
    print(f"SLOW_REQUEST_THRESHOLD=5.0")
    print(f"VERY_SLOW_REQUEST_THRESHOLD=10.0")

if with_tools_stats and with_tools_stats['count'] >= 10:
    print(f"\n# Tool request thresholds (Method 1 - Statistical)")
    print(f"SLOW_REQUEST_THRESHOLD_TOOLS={with_tools_stats['slow_statistical']:.1f}")
    print(f"VERY_SLOW_REQUEST_THRESHOLD_TOOLS={with_tools_stats['very_slow_statistical']:.1f}")
else:
    print(f"\n# Tool request thresholds (Defaults - insufficient data)")
    print(f"SLOW_REQUEST_THRESHOLD_TOOLS=30.0")
    print(f"VERY_SLOW_REQUEST_THRESHOLD_TOOLS=60.0")

print(f"\n💡 Next Steps:")
print(f"   1. Copy recommended thresholds to .env")
print(f"   2. Restart: ./stop-wrappers.sh && ./start-wrappers.sh")
print(f"   3. Verify: grep 'Performance Monitor initialized' logs/app.log | tail -1")
EOF
