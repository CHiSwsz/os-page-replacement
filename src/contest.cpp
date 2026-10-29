#include "paging.hpp"
#include "learned.hpp"

#include <array>
#include <charconv>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <set>
#include <stdexcept>
#include <unordered_map>
#include <variant>

namespace {
constexpr std::array<std::size_t, 5> capacities{5, 10, 20, 50, 100};
using Engine = std::variant<paging::OnlineAdaptive, paging::OnlineAdaptiveV5>;
const paging::Result& result(const Engine& engine) {
    return std::visit([](const auto& item) -> const paging::Result& { return item.result(); }, engine);
}
const char* help =
    "Usage: pager [--contest] FILE [--format text|csv|json]\n"
    "       [--page-format hex|decimal|token] [--seed UINT64]\n"
    "       [--window-factor 1..64] [--history-factor 1..64] [--adaptive-version 4|5]\n"
    "FILE may be '-' for standard input, or --trace FILE.\n"
    "Default: online Adaptive V5, frames 5,10,20,50,100, seed 0.\n"
    "One page per nonblank line; default hexadecimal, optional 0x prefix.\n"
    "UTF-8 BOM, CRLF, surrounding whitespace and blank lines are supported.\n"
    "token compares arbitrary non-whitespace labels exactly (uses O(unique labels) metadata).\n"
    "The five counts and their arithmetic mean are printed after valid EOF.\n";

std::uint64_t number(const std::string& text, const std::string& label) {
    std::uint64_t value = 0;
    const auto parsed = std::from_chars(text.data(), text.data()+text.size(), value);
    if (text.empty() || parsed.ec != std::errc{} || parsed.ptr != text.data()+text.size()) {
        throw std::invalid_argument("invalid " + label + ": " + text);
    }
    return value;
}

std::optional<paging::Page> token_page(std::string line, std::size_t number,
                                     std::unordered_map<std::string, paging::Page>& ids) {
    if (number == 1 && line.compare(0, 3, "\xef\xbb\xbf") == 0) line.erase(0, 3);
    const auto first = line.find_first_not_of(" \t\r\n\v\f");
    if (first == std::string::npos) return {};
    const auto last = line.find_last_not_of(" \t\r\n\v\f");
    auto token = line.substr(first, last-first+1);
    if (token.find_first_of(" \t\r\n\v\f") != std::string::npos) {
        throw std::invalid_argument("expected one page token on line " + std::to_string(number));
    }
    const auto found = ids.find(token);
    if (found != ids.end()) return found->second;
    const auto id = static_cast<paging::Page>(ids.size());
    ids.emplace(std::move(token), id);
    return id;
}
} // namespace

int contest_main(int argc, char** argv) {
    try {
        std::string path, format = "text", page_format = "hex";
        std::uint64_t seed = 0;
        paging::AdaptiveOptions options{4, 16, 5};
        std::set<std::string> seen;
        for (int i = 1; i < argc; ++i) {
            const std::string arg = argv[i];
            if (arg == "--help" || arg == "-h") { std::cout << help; return 0; }
            if (arg == "--contest") {
                if (!seen.insert(arg).second) throw std::invalid_argument("duplicate option: " + arg);
                continue;
            }
            if (arg == "-" || arg.empty() || arg[0] != '-') {
                if (!path.empty()) throw std::invalid_argument("provide exactly one trace file");
                path = arg;
                continue;
            }
            if (arg != "--trace" && arg != "--format" && arg != "--page-format" && arg != "--seed" &&
                arg != "--window-factor" && arg != "--history-factor" && arg != "--adaptive-version") throw std::invalid_argument("unknown option: " + arg);
            if (!seen.insert(arg).second) throw std::invalid_argument("duplicate option: " + arg);
            if (++i == argc) throw std::invalid_argument("missing value for " + arg);
            const std::string value = argv[i];
            if (arg == "--trace") {
                if (!path.empty()) throw std::invalid_argument("provide exactly one trace file");
                path = value;
            }
            if (arg == "--format") format = value;
            if (arg == "--page-format") page_format = value;
            if (arg == "--seed") seed = number(value, "seed");
            if (arg == "--adaptive-version") {
                const auto version = number(value, "adaptive version");
                if (version != 4 && version != 5) throw std::invalid_argument("contest adaptive version must be 4 or 5");
                options.version = static_cast<unsigned>(version);
            }
            if (arg == "--window-factor" || arg == "--history-factor") {
                const auto factor = number(value, "adaptive factor");
                if (factor == 0 || factor > 64) throw std::invalid_argument("adaptive factors must be in [1, 64]");
                if (arg == "--window-factor") options.window_factor = static_cast<std::size_t>(factor);
                else options.history_factor = static_cast<std::size_t>(factor);
            }
        }
        if (path.empty()) throw std::invalid_argument("a trace file is required; see pager --contest --help");
        if (format != "text" && format != "csv" && format != "json") throw std::invalid_argument("format must be text, csv or json");
        if (page_format != "hex" && page_format != "decimal" && page_format != "token") throw std::invalid_argument("page format must be hex, decimal or token");
        std::ifstream file;
        std::istream* input = &std::cin;
        if (path != "-") {
            file.open(path);
            if (!file) throw std::runtime_error("cannot open trace: " + path);
            input = &file;
        }
        std::vector<Engine> engines;
        for (const auto capacity : capacities) {
            if (options.version == 4) engines.emplace_back(std::in_place_type<paging::OnlineAdaptive>, capacity, seed, options);
            else engines.emplace_back(std::in_place_type<paging::OnlineAdaptiveV5>, capacity, seed, options);
        }
        std::unordered_map<std::string, paging::Page> token_ids;
        std::string line;
        std::size_t line_number = 0;
        while (std::getline(*input, line)) {
            ++line_number;
            const auto page = page_format == "token" ? token_page(line, line_number, token_ids)
                : paging::parse_page_line(line, line_number, page_format == "decimal" ? 10 : 16);
            if (page) for (auto& engine : engines) std::visit([&](auto& item) { item.access(*page); }, engine);
        }
        if (input->bad()) throw std::runtime_error("failed to read trace");
        long double total = 0;
        for (const auto& engine : engines) total += static_cast<long double>(result(engine).faults);
        const auto average = total / capacities.size();
        std::cout << std::setprecision(12);
        if (format == "json") {
            std::cout << "{\"algorithm\":\"adaptive\",\"version\":" << options.version << ",\"seed\":" << seed
                      << ",\"references\":" << result(engines[0]).references << ",\"results\":[";
            for (std::size_t i = 0; i < capacities.size(); ++i) {
                const auto& r = result(engines[i]);
                if (i) std::cout << ',';
                std::cout << "{\"frames\":" << capacities[i] << ",\"faults\":" << r.faults
                          << ",\"hits\":" << r.hits << ",\"evictions\":" << r.evictions
                          << ",\"fault_rate\":" << r.fault_rate() << '}';
            }
            std::cout << "],\"average_faults\":" << average << "}\n";
        } else if (format == "csv") {
            std::cout << "frames,references,faults,hits,evictions,fault_rate\n";
            for (std::size_t i = 0; i < capacities.size(); ++i) {
                const auto& r = result(engines[i]);
                std::cout << capacities[i] << ',' << r.references << ',' << r.faults << ',' << r.hits
                          << ',' << r.evictions << ',' << r.fault_rate() << '\n';
            }
            std::cout << "average,," << average << ",,,\n";
        } else {
            std::cout << "Adaptive V" << options.version << " | online demand paging | seed=" << seed << '\n'
                      << "References: " << result(engines[0]).references << '\n'
                      << "    Frames       Page faults       Fault rate\n";
            for (std::size_t i = 0; i < capacities.size(); ++i) {
                const auto& r = result(engines[i]);
                std::cout << std::setw(10) << capacities[i] << std::setw(18) << r.faults
                          << std::setw(16) << std::fixed << std::setprecision(2) << r.fault_rate()*100 << "%\n";
            }
            std::cout << "Average page faults (5 capacities): " << std::fixed << std::setprecision(2) << average << '\n';
        }
        std::cout.flush();
        if (!std::cout) throw std::runtime_error("failed to write results");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 2;
    }
}
