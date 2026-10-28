#pragma once

#include <cstddef>
#include <array>
#include <cstdint>
#include <istream>
#include <optional>
#include <string>
#include <vector>

namespace paging {
using Page = std::uint64_t;
enum class Algorithm { Random, Fifo, Opt, Lfu, Lru, SecondChance, Adaptive };
const char* name(Algorithm algorithm);
Algorithm parse_algorithm(const std::string& value);
std::vector<Page> read_trace(std::istream& input);

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
    double fault_rate() const;
};

struct AdaptiveOptions {
    std::size_t window_factor = 4;   // Comparison window: max(32, factor * frames).
    std::size_t history_factor = 16; // Page-ID history: max(32, factor * frames).
};

// Starts with empty memory. No prefetching. Only OPT reads future references.
// LFU counts references during the current residency and breaks ties by LRU.
Result simulate(const std::vector<Page>& trace, std::size_t capacity,
                Algorithm algorithm, std::uint64_t seed = 0, bool record_events = false,
                AdaptiveOptions options = {});
Result simulate_adaptive(const std::vector<Page>& trace, std::size_t capacity,
                         std::uint64_t seed, bool record_events, AdaptiveOptions options);
}  // namespace paging
