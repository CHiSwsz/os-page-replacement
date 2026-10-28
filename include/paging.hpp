#pragma once

#include <cstddef>
#include <array>
#include <cstdint>
#include <istream>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace paging {
using Page = std::uint64_t;
enum class Algorithm { Random, Fifo, Opt, Lfu, Lru, SecondChance, Adaptive };
const char* name(Algorithm algorithm);
Algorithm parse_algorithm(const std::string& value);
std::vector<Page> read_trace(std::istream& input);
std::optional<Page> parse_page_line(std::string line, std::size_t line_number, unsigned base = 16);

struct Event {
    std::size_t reference;  // One-based trace position.
    Page page;
    bool hit;
    std::size_t frame;      // Zero-based physical frame index.
    std::optional<Page> evicted;
};

struct Result {
    std::size_t references = 0;
    std::size_t hits = 0;
    std::size_t faults = 0;
    std::size_t evictions = 0;
    std::vector<Event> events;
    std::array<std::size_t, 3> policy_uses{};  // Adaptive: Random, LRU, reuse prediction.
    std::size_t policy_switches = 0;
    std::size_t history_peak = 0;
    std::array<std::size_t, 7> expert_uses{}; // V4: Random, LRU, gap, replay, frequency, cold prior, signature.
    std::array<std::size_t, 7> expert_faults{};
    std::size_t context_predictions = 0;
    std::size_t context_history_peak = 0;
    std::size_t signature_history_peak = 0;
    double fault_rate() const;
};

struct AdaptiveOptions {
    std::size_t window_factor = 4;   // V4 score horizon: 2 * max(32, factor * frames).
    std::size_t history_factor = 16; // V3/V4 halve this factor when frames > 20, rounding down to >= 1.
    unsigned version = 4;           // V1-V3 retained for exact historical reproduction.
};

// The V4 engine receives exactly one current page per call. It has no trace
// pointer, file handle, trace length, or means of examining future references.
class OnlineAdaptive {
    struct Impl;
    std::unique_ptr<Impl> impl_;
public:
    explicit OnlineAdaptive(std::size_t capacity, std::uint64_t seed = 0,
                            AdaptiveOptions options = {});
    ~OnlineAdaptive();
    OnlineAdaptive(OnlineAdaptive&&) noexcept;
    OnlineAdaptive& operator=(OnlineAdaptive&&) noexcept;
    OnlineAdaptive(const OnlineAdaptive&) = delete;
    OnlineAdaptive& operator=(const OnlineAdaptive&) = delete;
    Event access(Page page);
    const Result& result() const;
};

// Starts with empty memory. No prefetching. Only OPT reads future references.
// LFU counts references during the current residency and breaks ties by LRU.
Result simulate(const std::vector<Page>& trace, std::size_t capacity,
                Algorithm algorithm, std::uint64_t seed = 0, bool record_events = false,
                AdaptiveOptions options = {});
Result simulate_adaptive(const std::vector<Page>& trace, std::size_t capacity,
                         std::uint64_t seed, bool record_events, AdaptiveOptions options);
}  // namespace paging
