#include "paging.hpp"

#include <charconv>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>

namespace {
const char* usage =
    "Usage: pager --trace FILE --algorithm random|fifo|opt|min|lfu|lru|second_chance|adaptive|all\n"
    "             --frames N[,N...] [--seed UINT64] [--events FILE]\n"
    "             [--window-factor 1..64] [--history-factor 1..64] [--adaptive-version 1|2]\n"
    "Trace: one hexadecimal virtual page number per nonblank line.\n"
    "CSV results go to stdout; errors go to stderr. Initial memory is empty.\n"
    "--events requires one algorithm and one frame count; frame IDs start at 0.\n"
    "LFU counts current-residency references and breaks frequency ties by LRU.\n";

std::uint64_t number(const std::string& text, const std::string& label) {
    std::uint64_t value = 0;
    const auto parsed = std::from_chars(text.data(), text.data() + text.size(), value, 10);
    if (text.empty() || parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size()) {
        throw std::invalid_argument("invalid " + label + ": " + text);
    }
    return value;
}

std::vector<std::size_t> frame_counts(const std::string& text) {
    if (text.empty() || text.back() == ',') throw std::invalid_argument("invalid frame list");
    std::istringstream input(text);
    std::string token;
    std::vector<std::size_t> values;
    std::set<std::size_t> unique;
    while (std::getline(input, token, ',')) {
        const auto value = number(token, "frame count");
        if (value == 0 || value > std::numeric_limits<std::size_t>::max()) {
            throw std::invalid_argument("frame count must be a positive size_t");
        }
        const auto count = static_cast<std::size_t>(value);
        if (!unique.insert(count).second) throw std::invalid_argument("duplicate frame count");
        values.push_back(count);
    }
    return values;
}
}  // namespace

int main(int argc, char** argv) {
    try {
        std::string trace_path, algorithm_text, frames_text, events_path;
        std::uint64_t seed = 0;
        paging::AdaptiveOptions adaptive_options;
        std::set<std::string> seen;
        for (int i = 1; i < argc; ++i) {
            const std::string arg = argv[i];
            if (arg == "--help" || arg == "-h") { std::cout << usage; return 0; }
            if (arg != "--trace" && arg != "--algorithm" && arg != "--frames" &&
                arg != "--seed" && arg != "--events" && arg != "--window-factor" && arg != "--history-factor" && arg != "--adaptive-version") {
                throw std::invalid_argument("unknown option: " + arg);
            }
            if (!seen.insert(arg).second) throw std::invalid_argument("duplicate option: " + arg);
            if (++i == argc) throw std::invalid_argument("missing value for " + arg);
            const std::string value = argv[i];
            if (arg == "--trace") trace_path = value;
            if (arg == "--algorithm") algorithm_text = value;
            if (arg == "--frames") frames_text = value;
            if (arg == "--events") events_path = value;
            if (arg == "--seed") seed = number(value, "seed");
            if (arg == "--adaptive-version") {
                const auto version = number(value, "adaptive version");
                if (version != 1 && version != 2) throw std::invalid_argument("adaptive version must be 1 or 2");
                adaptive_options.aligned_comparison = version == 2;
            }
            if (arg == "--window-factor" || arg == "--history-factor") {
                const auto factor = number(value, "adaptive factor");
                if (factor == 0 || factor > 64) throw std::invalid_argument("adaptive factors must be in [1, 64]");
                if (arg == "--window-factor") adaptive_options.window_factor = static_cast<std::size_t>(factor);
                else adaptive_options.history_factor = static_cast<std::size_t>(factor);
            }
        }
        if (trace_path.empty() || algorithm_text.empty() || frames_text.empty()) {
            throw std::invalid_argument("--trace, --algorithm and --frames are required");
        }
        const auto capacities = frame_counts(frames_text);
        std::vector<paging::Algorithm> algorithms;
        if (algorithm_text == "all") {
            algorithms = {paging::Algorithm::Random, paging::Algorithm::Fifo, paging::Algorithm::Opt,
                          paging::Algorithm::Lfu, paging::Algorithm::Lru, paging::Algorithm::SecondChance,
                          paging::Algorithm::Adaptive};
        } else {
            algorithms.push_back(paging::parse_algorithm(algorithm_text));
        }
        if (seen.count("--events") && events_path.empty()) throw std::invalid_argument("empty events path");
        if (!events_path.empty() && (algorithms.size() != 1 || capacities.size() != 1)) {
            throw std::invalid_argument("--events requires one algorithm and one frame count");
        }
        std::ifstream input(trace_path);
        if (!input) throw std::runtime_error("cannot open trace: " + trace_path);
        const auto trace = paging::read_trace(input);
        std::ofstream events;
        if (!events_path.empty()) {
            if (std::filesystem::exists(events_path) && std::filesystem::equivalent(trace_path, events_path)) {
                throw std::invalid_argument("events output must not overwrite the input trace");
            }
            events.open(events_path);
            if (!events) throw std::runtime_error("cannot open events output: " + events_path);
            events << "reference,page,hit,frame,evicted\n";
        }
        std::cout << "algorithm,frames,seed,references,hits,faults,evictions,fault_rate,policy_random,policy_lru,policy_predict,policy_switches,history_peak\n";
        std::cout << std::setprecision(12);
        for (const auto algorithm : algorithms) {
            for (const auto capacity : capacities) {
                const auto result = paging::simulate(trace, capacity, algorithm, seed, !events_path.empty(), adaptive_options);
                std::cout << paging::name(algorithm) << ',' << capacity << ',';
                if (algorithm == paging::Algorithm::Random || algorithm == paging::Algorithm::Adaptive) std::cout << seed;
                std::cout << ',' << result.references << ',' << result.hits << ',' << result.faults
                          << ',' << result.evictions << ',' << result.fault_rate();
                for (const auto uses : result.policy_uses) std::cout << ',' << uses;
                std::cout << ',' << result.policy_switches << ',' << result.history_peak << '\n';
                if (!events_path.empty()) {
                    for (const auto& event : result.events) {
                        events << event.reference << ',' << std::hex << event.page << std::dec << ','
                               << (event.hit ? 1 : 0) << ',' << event.frame << ',';
                        if (event.evicted) events << std::hex << *event.evicted << std::dec;
                        events << '\n';
                    }
                }
            }
        }
        if (!events_path.empty()) { events.flush(); if (!events) throw std::runtime_error("failed to write events"); }
        std::cout.flush();
        if (!std::cout) throw std::runtime_error("failed to write results");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 2;
    }
}
