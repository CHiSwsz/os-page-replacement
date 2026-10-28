#include "paging.hpp"

#include <algorithm>
#include <charconv>
#include <limits>
#include <random>
#include <stdexcept>
#include <tuple>
#include <unordered_map>

namespace paging {
const char* name(Algorithm algorithm) {
    switch (algorithm) {
        case Algorithm::Random: return "random";
        case Algorithm::Fifo: return "fifo";
        case Algorithm::Opt: return "opt";
        case Algorithm::Lfu: return "lfu";
        case Algorithm::Lru: return "lru";
        case Algorithm::SecondChance: return "second_chance";
        case Algorithm::Adaptive: return "adaptive";
    }
    throw std::invalid_argument("unknown algorithm");
}

Algorithm parse_algorithm(const std::string& value) {
    if (value == "random") return Algorithm::Random;
    if (value == "fifo") return Algorithm::Fifo;
    if (value == "opt" || value == "min") return Algorithm::Opt;
    if (value == "lfu") return Algorithm::Lfu;
    if (value == "lru") return Algorithm::Lru;
    if (value == "second_chance" || value == "second-chance" || value == "clock") return Algorithm::SecondChance;
    if (value == "adaptive") return Algorithm::Adaptive;
    throw std::invalid_argument("unknown algorithm: " + value);
}

std::vector<Page> read_trace(std::istream& input) {
    std::vector<Page> trace;
    std::string line;
    std::size_t line_number = 0;
    while (std::getline(input, line)) {
        ++line_number;
        const auto first = line.find_first_not_of(" \t\r\n\v\f");
        if (first == std::string::npos) continue;
        const auto last = line.find_last_not_of(" \t\r\n\v\f");
        std::string token = line.substr(first, last - first + 1);
        if (token.size() >= 2 && token[0] == '0' && (token[1] == 'x' || token[1] == 'X')) {
            token.erase(0, 2);
        }
        Page page = 0;
        const auto parsed = std::from_chars(token.data(), token.data() + token.size(), page, 16);
        if (token.empty() || parsed.ec != std::errc{} || parsed.ptr != token.data() + token.size()) {
            throw std::invalid_argument("invalid hexadecimal page number on line " + std::to_string(line_number));
        }
        trace.push_back(page);
    }
    if (input.bad()) throw std::runtime_error("failed to read trace");
    return trace;
}

double Result::fault_rate() const {
    return references == 0 ? 0.0 : static_cast<double>(faults) / static_cast<double>(references);
}

namespace {
struct Frame {
    Page page;
    std::size_t loaded_at;
    std::size_t last_used;
    std::size_t frequency;
    std::size_t next_use;
    bool referenced = true;
};

// Rejection sampling avoids modulo bias and implementation-specific behavior
// of std::uniform_int_distribution. Seeds reproduce the same choices across
// standard libraries that implement the specified mt19937_64 engine.
std::size_t random_slot(std::mt19937_64& rng, std::size_t count) {
    const auto bound = static_cast<std::uint64_t>(count);
    const std::uint64_t threshold = (std::uint64_t{0} - bound) % bound;
    std::uint64_t draw;
    do { draw = rng(); } while (draw < threshold);
    return static_cast<std::size_t>(draw % bound);
}
}  // namespace

Result simulate(const std::vector<Page>& trace, std::size_t capacity,
                Algorithm algorithm, std::uint64_t seed, bool record_events, AdaptiveOptions options) {
    if (capacity == 0) throw std::invalid_argument("frame count must be positive");
    (void)name(algorithm);  // Reject invalid enum values even for empty traces.
    if (algorithm == Algorithm::Adaptive) return simulate_adaptive(trace, capacity, seed, record_events, options);
    Result result;
    result.references = trace.size();
    if (record_events) result.events.reserve(trace.size());
    std::vector<Frame> frames;
    frames.reserve(std::min(capacity, trace.size()));
    std::unordered_map<Page, std::size_t> resident;
    resident.reserve(std::min(capacity, trace.size()));
    std::mt19937_64 rng(seed);
    std::size_t clock_hand = 0;

    // trace.size() means "never used again" and sorts after every real index.
    std::vector<std::size_t> next_use;
    if (algorithm == Algorithm::Opt) {
        next_use.assign(trace.size(), trace.size());
        std::unordered_map<Page, std::size_t> next_position;
        for (std::size_t i = trace.size(); i > 0;) {
            --i;
            const auto found = next_position.find(trace[i]);
            if (found != next_position.end()) next_use[i] = found->second;
            next_position[trace[i]] = i;
        }
    }

    for (std::size_t i = 0; i < trace.size(); ++i) {
        const Page page = trace[i];
        const auto found = resident.find(page);
        const bool hit = found != resident.end();
        std::size_t slot;
        std::optional<Page> evicted;
        if (hit) {
            ++result.hits;
            slot = found->second;
            ++frames[slot].frequency;
            frames[slot].last_used = i;
            frames[slot].referenced = true;
        } else {
            ++result.faults;
            if (frames.size() < capacity) {
                slot = frames.size();
                frames.push_back(Frame{page, i, i, 1, trace.size()});
            } else {
                slot = 0;
                if (algorithm == Algorithm::Random) {
                    slot = random_slot(rng, frames.size());
                } else if (algorithm == Algorithm::SecondChance) {
                    while (frames[clock_hand].referenced) {
                        frames[clock_hand].referenced = false;
                        clock_hand = (clock_hand + 1) % frames.size();
                    }
                    slot = clock_hand;
                    clock_hand = (clock_hand + 1) % frames.size();
                } else {
                    for (std::size_t j = 1; j < frames.size(); ++j) {
                        bool prefer = false;
                        switch (algorithm) {
                            case Algorithm::Fifo:
                                prefer = frames[j].loaded_at < frames[slot].loaded_at;
                                break;
                            case Algorithm::Lru:
                                prefer = frames[j].last_used < frames[slot].last_used;
                                break;
                            case Algorithm::Lfu:
                                prefer = std::tie(frames[j].frequency, frames[j].last_used) <
                                         std::tie(frames[slot].frequency, frames[slot].last_used);
                                break;
                            case Algorithm::Opt:
                                prefer = frames[j].next_use > frames[slot].next_use;
                                break;
                            case Algorithm::Random:
                            case Algorithm::SecondChance:
                            case Algorithm::Adaptive: break;
                        }
                        if (prefer) slot = j;
                    }
                }
                evicted = frames[slot].page;
                resident.erase(*evicted);
                frames[slot] = Frame{page, i, i, 1, trace.size()};
                ++result.evictions;
            }
            resident[page] = slot;
        }
        if (algorithm == Algorithm::Opt) frames[slot].next_use = next_use[i];
        if (record_events) result.events.push_back(Event{i + 1, page, hit, slot, evicted});
    }
    return result;
}
}  // namespace paging
