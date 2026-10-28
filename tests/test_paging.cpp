#include "paging.hpp"

#include <algorithm>
#include <array>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <tuple>

using paging::Algorithm;
using paging::Page;
using Trace = std::vector<Page>;
const std::array<Algorithm, 5> algorithms = {
    Algorithm::Random, Algorithm::Fifo, Algorithm::Opt, Algorithm::Lfu, Algorithm::Lru};
std::size_t checks = 0;

void check(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}

// Independent oracle: explore every legal victim, with no knowledge of MIN's rule.
std::size_t optimal_faults(const Trace& trace, std::size_t capacity) {
    using State = std::pair<std::size_t, std::set<Page>>;
    std::map<State, std::size_t> memo;
    const auto solve = [&](const auto& self, std::size_t i, std::set<Page> resident) -> std::size_t {
        if (i == trace.size()) return 0;
        const State key{i, resident};
        if (const auto found = memo.find(key); found != memo.end()) return found->second;
        std::size_t cost;
        if (resident.count(trace[i])) {
            cost = self(self, i + 1, resident);
        } else if (resident.size() < capacity) {
            resident.insert(trace[i]);
            cost = 1 + self(self, i + 1, resident);
        } else {
            cost = trace.size();
            for (const Page victim : resident) {
                auto changed = resident;
                changed.erase(victim);
                changed.insert(trace[i]);
                cost = std::min(cost, 1 + self(self, i + 1, changed));
            }
        }
        memo[key] = cost;
        return cost;
    };
    return solve(solve, 0, {});
}

// Slow, independent reference: an arrival-order list and explicit access histories.
std::vector<std::optional<Page>> reference_victims(const Trace& trace, std::size_t capacity, Algorithm algorithm) {
    std::vector<Page> resident;
    std::map<Page, std::vector<std::size_t>> histories;
    std::vector<std::optional<Page>> victims;
    for (std::size_t i = 0; i < trace.size(); ++i) {
        std::optional<Page> victim;
        if (std::find(resident.begin(), resident.end(), trace[i]) == resident.end()) {
            if (resident.size() == capacity) {
                auto selected = resident.begin();
                if (algorithm != Algorithm::Fifo) {
                    selected = std::min_element(resident.begin(), resident.end(), [&](Page a, Page b) {
                        if (algorithm == Algorithm::Lru) return histories[a].back() < histories[b].back();
                        return std::make_pair(histories[a].size(), histories[a].back()) <
                               std::make_pair(histories[b].size(), histories[b].back());
                    });
                }
                victim = *selected;
                histories.erase(*selected);
                resident.erase(selected);
            }
            resident.push_back(trace[i]);
        }
        histories[trace[i]].push_back(i);
        victims.push_back(victim);
    }
    return victims;
}

void validate_events(const Trace& trace, std::size_t capacity, const paging::Result& result) {
    check(result.events.size() == trace.size(), "one event per reference");
    check(result.hits + result.faults == trace.size(), "hits + faults must equal references");
    std::map<std::size_t, Page> frames;
    std::size_t hits = 0, evictions = 0;
    for (std::size_t i = 0; i < trace.size(); ++i) {
        const auto& event = result.events[i];
        const bool was_resident = std::any_of(frames.begin(), frames.end(), [&](const auto& entry) {
            return entry.second == trace[i];
        });
        check(event.reference == i + 1 && event.page == trace[i], "event identity");
        check(event.frame < capacity, "frame within capacity");
        check(event.hit == was_resident, "hit agrees with pre-access memory");
        if (was_resident) {
            ++hits;
            check(!event.evicted && frames.at(event.frame) == trace[i], "hit must not evict or move page");
        } else {
            check(event.evicted.has_value() == (frames.size() == capacity), "evict only when full");
            if (event.evicted) {
                ++evictions;
                check(frames.at(event.frame) == *event.evicted, "victim must occupy the replaced frame");
            } else {
                check(!frames.count(event.frame), "fill an empty frame");
            }
            frames[event.frame] = trace[i];
        }
        check(frames.size() <= capacity, "capacity bound");
    }
    check(result.hits == hits && result.evictions == evictions, "event totals agree");
}

void exhaustive() {
    std::size_t trace_count = 0;
    // All 1,093 traces of length 0..6 over three distinct page IDs.
    for (std::size_t length = 0, count = 1; length <= 6; ++length, count *= 3) {
        for (std::size_t code = 0; code < count; ++code) {
            Trace trace(length);
            auto digits = code;
            for (auto& page : trace) { page = digits % 3; digits /= 3; }
            ++trace_count;
            for (std::size_t capacity = 1; capacity <= 4; ++capacity) {
                const auto optimum = optimal_faults(trace, capacity);
                for (const auto algorithm : algorithms) {
                    const auto result = paging::simulate(trace, capacity, algorithm, 17, true);
                    validate_events(trace, capacity, result);
                    check(result.faults >= optimum, "algorithm cannot beat offline optimum");
                    if (algorithm == Algorithm::Opt) check(result.faults == optimum, "OPT equals exhaustive optimum");
                    if (algorithm == Algorithm::Fifo || algorithm == Algorithm::Lfu || algorithm == Algorithm::Lru) {
                        const auto expected = reference_victims(trace, capacity, algorithm);
                        for (std::size_t i = 0; i < trace.size(); ++i) {
                            check(result.events[i].evicted == expected[i], "victim differs from independent reference");
                        }
                    }
                }
            }
        }
    }
    check(trace_count == 1093, "exhaustive trace count");
}

int main() {
    try {
        const Trace belady{1,2,3,4,1,2,5,1,2,3,4,5};
        check(paging::simulate(belady, 3, Algorithm::Fifo).faults == 9, "FIFO at 3 frames");
        check(paging::simulate(belady, 4, Algorithm::Fifo).faults == 10, "FIFO Belady anomaly");
        check(paging::simulate(belady, 3, Algorithm::Opt).faults == 7, "known OPT count");
        check(paging::simulate(belady, 3, Algorithm::Lru).faults == 10, "known LRU count");
        const Trace example{10,10,10,10,11,11,11,12,10,12,13};
        check(paging::simulate(example, 3, Algorithm::Fifo, 0, true).events.back().evicted == 10, "FIFO uses arrival time");
        check(paging::simulate(example, 3, Algorithm::Lru, 0, true).events.back().evicted == 11, "LRU uses last access");
        check(paging::simulate(example, 3, Algorithm::Lfu, 0, true).events.back().evicted == 12, "LFU uses counts");
        check(paging::simulate({1,2,1,2,3}, 2, Algorithm::Lfu, 0, true).events.back().evicted == 1, "LFU tie uses LRU");
        const auto reset = paging::simulate({1,1,2,2,2,3,1,4}, 2, Algorithm::Lfu, 0, true);
        check(reset.events.back().evicted == 1, "LFU resets count after eviction and reload");
        for (const auto algorithm : algorithms) {
            check(paging::simulate({}, 5, algorithm).fault_rate() == 0, "empty trace");
            check(paging::simulate({42,42,42}, 1, algorithm).faults == 1, "repeated page");
            check(paging::simulate({0,0xffffffffffffffffULL,0}, 10, algorithm).faults == 2, "large and zero IDs");
        }
        bool rejected = false;
        try { (void)paging::simulate({}, 0, Algorithm::Lru); } catch (const std::invalid_argument&) { rejected = true; }
        check(rejected, "reject zero frames");
        std::istringstream valid(" 2001f86\r\n\n0xAbC\nabc\nFFFFFFFFFFFFFFFF\n0\n");
        check(paging::read_trace(valid) == Trace({0x2001f86,0xabc,0xabc,0xffffffffffffffffULL,0}), "hex parsing and whitespace");
        for (const auto* token : {"-1", "+1", "0x", "xyz", "1 2", "10000000000000000"}) {
            std::istringstream invalid(token);
            rejected = false;
            try { (void)paging::read_trace(invalid); } catch (const std::invalid_argument&) { rejected = true; }
            check(rejected, "reject invalid page token");
        }
        std::set<Page> random_victims;
        for (std::uint64_t seed = 0; seed < 100; ++seed) {
            const auto a = paging::simulate(belady, 3, Algorithm::Random, seed, true);
            const auto b = paging::simulate(belady, 3, Algorithm::Random, seed, true);
            for (std::size_t i = 0; i < a.events.size(); ++i) {
                check(a.events[i].evicted == b.events[i].evicted, "seed reproducibility");
            }
            random_victims.insert(*paging::simulate({1,2,3,4}, 3, Algorithm::Random, seed, true).events.back().evicted);
        }
        check(random_victims.size() == 3, "random can select every resident page");
        exhaustive();
        std::cout << "PASS: " << checks << " checks, including 1,093 exhaustive traces across 4 capacities and 5 algorithms\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
