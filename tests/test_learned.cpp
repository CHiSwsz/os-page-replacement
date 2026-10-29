#include "learned.hpp"
#include <algorithm>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <random>
#include <set>
#include <stdexcept>

namespace {
std::size_t checks = 0;
void require(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}
// Independent dynamic program over every legal eviction, for short traces.
std::size_t optimum(const std::vector<paging::Page>& trace, std::size_t capacity) {
    std::map<std::set<paging::Page>, std::size_t> states{{{}, 0}};
    for (auto page : trace) {
        std::map<std::set<paging::Page>, std::size_t> next;
        auto add = [&](std::set<paging::Page> memory, std::size_t cost) {
            auto found = next.find(memory);
            if (found == next.end()) next.emplace(std::move(memory), cost);
            else found->second = std::min(found->second, cost);
        };
        for (const auto& state : states) {
            if (state.first.count(page)) add(state.first, state.second);
            else if (state.first.size() < capacity) {
                auto memory = state.first; memory.insert(page); add(memory, state.second + 1);
            } else for (auto victim : state.first) {
                auto memory = state.first; memory.erase(victim); memory.insert(page); add(memory, state.second + 1);
            }
        }
        states = std::move(next);
    }
    std::size_t best = trace.size();
    for (const auto& state : states) best = std::min(best, state.second);
    return best;
}
std::vector<paging::Event> validate(const std::vector<paging::Page>& trace, std::size_t capacity,
                                  std::uint64_t seed, paging::AdaptiveOptions options = {4,16,5}) {
    paging::OnlineAdaptiveV5 engine(capacity, seed, options);
    std::map<std::size_t, paging::Page> physical;
    std::set<paging::Page> residents;
    std::vector<paging::Event> events;
    std::size_t faults = 0, evictions = 0;
    for (std::size_t i = 0; i < trace.size(); ++i) {
        const auto event = engine.access(trace[i]);
        const bool hit = residents.count(trace[i]) != 0;
        require(event.page == trace[i] && event.reference == i+1, "event reference");
        require(event.hit == hit && event.frame < capacity, "physical hit and frame");
        if (hit) require(!event.evicted && physical.at(event.frame) == trace[i], "hit cannot load or evict");
        else {
            ++faults;
            if (residents.size() == capacity) {
                require(event.evicted.has_value() && physical.at(event.frame) == *event.evicted, "evict real resident");
                require(residents.erase(*event.evicted) == 1, "one eviction");
                ++evictions;
            } else require(!event.evicted && !physical.count(event.frame), "fill empty frame");
            residents.insert(trace[i]); physical[event.frame] = trace[i];
        }
        require(residents.size() <= capacity && residents.count(trace[i]) == 1, "demand-only memory");
        require(engine.result().faults == faults && engine.result().evictions == evictions, "fault accounting");
        events.push_back(event);
    }
    const auto& result = engine.result();
    const auto& diagnostic = engine.diagnostics();
    require(result.references == trace.size() && result.hits+result.faults == trace.size(), "total accounting");
    require(std::accumulate(result.policy_uses.begin(), result.policy_uses.end(), std::size_t{0}) == trace.size(), "policy counters");
    require(std::accumulate(diagnostic.expert_uses.begin(), diagnostic.expert_uses.end(), std::size_t{0}) == trace.size(), "expert counters");
    if (capacity < 1000000) {
        const auto h = std::max(std::size_t{32}, capacity*(capacity>20 ? std::max(std::size_t{1},options.history_factor/2) : options.history_factor));
        require(result.history_peak <= h && diagnostic.model_peak <= 16*h, "bounded learning metadata");
        require(result.context_history_peak <= std::max(std::size_t{256},4*h) && result.signature_history_peak <= h, "bounded V4 metadata");
    }
    return events;
}
bool same(const paging::Event& a, const paging::Event& b) {
    return a.page==b.page && a.reference==b.reference && a.hit==b.hit && a.frame==b.frame && a.evicted==b.evicted;
}
void exhaustive(std::vector<paging::Page>& trace) {
    for (auto capacity : {1U,2U,3U,4U}) {
        const auto lower = optimum(trace,capacity);
        for (auto seed : {0U,17U}) {
            const auto events = validate(trace,capacity,seed);
            const auto misses = static_cast<std::size_t>(std::count_if(events.begin(),events.end(),[](const auto& e){return !e.hit;}));
            require(misses >= lower, "cannot beat exact offline lower bound");
        }
    }
    if (trace.size() == 7) return;
    for (auto page : {0U,1U,2U}) { trace.push_back(page); exhaustive(trace); trace.pop_back(); }
}
}
int main() {
    try {
        std::vector<paging::Page> trace;
        exhaustive(trace);
        std::mt19937_64 rng(2026102905ULL);
        for (std::size_t i=0; i<6000; ++i) {
            if (i%1200<400) trace.push_back(i%173);
            else if (i%1200<800) trace.push_back(rng()%31);
            else trace.push_back((i%3==0 ? 500 : 0)+rng()%211);
        }
        for (auto capacity : {1U,5U,10U,20U,50U,100U}) for (auto history : {1U,16U,64U}) {
            const paging::AdaptiveOptions options{4,history,5};
            auto events = validate(trace,capacity,17,options);
            const std::vector<paging::Page> prefix(trace.begin(),trace.begin()+2111);
            const auto partial = validate(prefix,capacity,17,options);
            for (std::size_t i=0; i<partial.size(); ++i) require(same(partial[i],events[i]), "prefix invariance");
            auto renamed = trace;
            auto rename = [](paging::Page p) {return p*0x9e3779b97f4a7c15ULL+0xfedcba9876543210ULL;};
            for (auto& page:renamed) page=rename(page);
            const auto mapped = validate(renamed,capacity,17,options);
            for (std::size_t i=0; i<events.size(); ++i) {
                auto transformed=events[i]; transformed.page=rename(transformed.page);
                if (transformed.evicted) transformed.evicted=rename(*transformed.evicted);
                require(same(transformed,mapped[i]), "page identity permutation invariance");
            }
            const auto vector_result=paging::simulate(trace,capacity,paging::Algorithm::Adaptive,17,true,options);
            require(vector_result.events.size()==events.size(), "stream/vector count");
            for (std::size_t i=0; i<events.size(); ++i) require(same(events[i],vector_result.events[i]), "stream/vector decisions");
        }
        validate({0,1,0,std::numeric_limits<paging::Page>::max()},std::numeric_limits<std::size_t>::max(),0);
        for (const auto options : {paging::AdaptiveOptions{0,16,5}, {4,0,5}, {65,16,5}, {4,65,5}, {4,16,4}}) {
            bool rejected=false;
            try { paging::OnlineAdaptiveV5 engine(5,0,options); } catch (const std::invalid_argument&) { rejected=true; }
            require(rejected,"invalid options rejected");
        }
        bool rejected=false;
        try { paging::OnlineAdaptiveV5 engine(0); } catch (const std::invalid_argument&) { rejected=true; }
        require(rejected,"zero frames rejected");
        std::cout << "PASS: V5 legal memory, exact OPT bound, prefixes, renaming, streaming, metadata; " << checks << " assertions\n";
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
