// V4 expert rules are retained here to keep the frozen V4 source byte-identical.
// V5 adds delayed-label experts and a faster controller; V4 remains reproducible.
#include "learned.hpp"
#include "reuse_model.hpp"

#include <algorithm>
#include <cmath>
#include <deque>
#include <limits>
#include <list>
#include <random>
#include <stdexcept>
#include <unordered_map>

namespace paging {
namespace {
constexpr std::size_t expert_count = learned_expert_count;
constexpr std::size_t context_length = 12;
constexpr std::size_t anchor_candidates = 8;
constexpr std::size_t context_factor = 4;
// Expert order: Random, LRU, EWMA gap, historical replay, decayed frequency,
// cold-page prior, and an anchor/offset signature learned on completed reuses.

std::size_t product(std::size_t a, std::size_t b) {
    const auto maximum = std::numeric_limits<std::size_t>::max();
    return a > maximum / b ? maximum : a * b;
}

std::size_t limit(std::size_t capacity, std::size_t factor) {
    if (capacity == 0) throw std::invalid_argument("frame count must be positive");
    if (factor == 0 || factor > 64) throw std::invalid_argument("adaptive factors must be in [1, 64]");
    return std::max(std::size_t{32}, product(capacity, factor));
}

// Shared observations, never a cache of page contents. Both the page records
// and the sequence of completed requests are bounded, independently of N.
class Observations {
    ReuseModel learned_;
    struct Signature {
        Page anchor;
        std::size_t distance;
        bool operator==(const Signature& other) const { return anchor == other.anchor && distance == other.distance; }
    };
    struct SignatureHash {
        std::size_t operator()(const Signature& s) const { return std::hash<Page>{}(s.anchor) ^ (s.distance * 2654435761U); }
    };
    struct SignatureRecord { double gap; std::list<Signature>::iterator position; };
    struct Record {
        std::size_t last;
        double gap = 0;
        double frequency = 1;
        bool repeated = false;
        std::list<Page>::iterator position;
        double cold_gap = 0;
        std::optional<Signature> signature;
        double signature_gap = std::numeric_limits<double>::infinity();
    };
    const std::size_t history_limit_, tape_limit_, horizon_;
    const double decay_scale_;
    std::list<Page> order_;
    std::unordered_map<Page, Record> records_;
    std::deque<Page> tape_;
    std::size_t base_ = 0;
    std::unordered_map<Page, std::deque<std::size_t>> positions_;
    std::unordered_map<Page, std::size_t> forecast_;
    std::size_t forecast_span_ = 0;
    std::deque<double> recent_gaps_;
    std::list<Signature> signature_order_;
    std::unordered_map<Signature, SignatureRecord, SignatureHash> signatures_;

    std::optional<Signature> signature() const {
        for (std::size_t distance = 1; distance <= 32 && distance <= tape_.size(); ++distance) {
            const Page anchor = tape_[tape_.size() - distance];
            const auto found = records_.find(anchor);
            if (found != records_.end() && found->second.frequency >= 3) return Signature{anchor, distance};
        }
        return {};
    }

    void train_signature(const std::optional<Signature>& signature, double gap) {
        if (!signature) return;
        const auto found = signatures_.find(*signature);
        if (found != signatures_.end()) {
            found->second.gap = 0.5 * found->second.gap + 0.5 * gap;
            signature_order_.splice(signature_order_.end(), signature_order_, found->second.position);
        } else {
            if (signatures_.size() == history_limit_) {
                signatures_.erase(signature_order_.front());
                signature_order_.pop_front();
            }
            signature_order_.push_back(*signature);
            signatures_.emplace(*signature, SignatureRecord{gap, std::prev(signature_order_.end())});
        }
    }
public:
    Observations(std::size_t capacity, std::size_t history_factor)
        : learned_(capacity, history_factor), history_limit_(limit(capacity, history_factor)),
          tape_limit_(std::max(std::size_t{256}, product(history_limit_, context_factor))),
          horizon_(std::max(std::size_t{32}, product(capacity, 4))),
          decay_scale_(static_cast<double>(std::max(std::size_t{32}, product(capacity, 8)))) {}

    std::size_t model_size() const { return learned_.model_size(); }
    std::size_t size() const { return records_.size(); }
    std::size_t tape_size() const { return tape_.size(); }
    std::size_t signature_size() const { return signatures_.size(); }
    bool predicts() const { return forecast_span_ != 0; }

    void prepare(Page page, std::size_t now) {
        learned_.prepare(page, now);
        forecast_.clear();
        forecast_span_ = 0;
        const auto found = positions_.find(page);
        if (found == positions_.end()) return;
        std::size_t anchor = 0, matched = 0, examined = 0;
        for (auto it = found->second.rbegin(); it != found->second.rend() && examined < anchor_candidates; ++it, ++examined) {
            const auto previous = *it;
            if (previous + 1 >= now) continue;
            std::size_t length = 1;
            while (length < context_length && previous - base_ >= length && now - base_ >= length &&
                   tape_[previous - length - base_] == tape_[now - length - base_]) ++length;
            if (length > matched) { anchor = previous; matched = length; }
            if (matched == context_length) break;
        }
        if (matched < 2) return;
        // Every copied reference is strictly before 'now'. The past suffix is
        // a forecast, not the actual future, and may be entirely wrong.
        forecast_span_ = std::min(horizon_, now - anchor - 1);
        for (std::size_t distance = 1; distance <= forecast_span_; ++distance) {
            forecast_.emplace(tape_[anchor + distance - base_], distance);
        }
    }

    double delay(Page page, std::size_t now) const {
        const auto found = records_.find(page);
        if (found == records_.end() || !found->second.repeated) return std::numeric_limits<double>::infinity();
        const auto& record = found->second;
        const double age = static_cast<double>(now - record.last);
        return age < record.gap ? record.gap - age : age;
    }

    double score(Page page, std::size_t now, std::size_t policy) const {
        if (policy >= 7) return learned_.score(page, now, policy - 7);
        if (policy == 6) {
            const auto found = records_.find(page);
            if (found == records_.end()) return std::numeric_limits<double>::infinity();
            const auto& record = found->second;
            const double age = static_cast<double>(now - record.last);
            const double estimate = std::isfinite(record.signature_gap) ? record.signature_gap : (record.repeated ? record.gap : std::numeric_limits<double>::infinity());
            return age < estimate ? estimate - age : age;
        }
        if (policy == 5) {
            const auto found = records_.find(page);
            if (found == records_.end()) return std::numeric_limits<double>::infinity();
            const auto& record = found->second;
            const double age = static_cast<double>(now - record.last);
            const double estimate = record.repeated ? record.gap
                : (record.cold_gap > 0 ? record.cold_gap : std::numeric_limits<double>::infinity());
            return age < estimate ? estimate - age : age;
        }
        if (policy == 3 && forecast_span_) {
            const auto predicted = forecast_.find(page);
            if (predicted != forecast_.end()) return static_cast<double>(predicted->second);
            return static_cast<double>(forecast_span_) + delay(page, now);
        }
        if (policy == 4) {
            const auto found = records_.find(page);
            if (found == records_.end()) return std::numeric_limits<double>::infinity();
            const auto& record = found->second;
            // A log score avoids overflow when a formerly hot page goes cold.
            return static_cast<double>(now - record.last) / decay_scale_ - std::log2(record.frequency);
        }
        return delay(page, now);
    }

    void observe(Page page, std::size_t now) {
        learned_.observe(page, now);
        const auto current_signature = signature();
        const auto found = records_.find(page);
        if (found == records_.end()) {
            if (records_.size() == history_limit_) {
                records_.erase(order_.front());
                order_.pop_front();
            }
            order_.push_back(page);
            records_.emplace(page, Record{now, 0, 1, false, std::prev(order_.end()),
                                         0, {}, std::numeric_limits<double>::infinity()});
        } else {
            auto& record = found->second;
            const double gap = static_cast<double>(now - record.last);
            // The interval becomes a training label only when the page really
            // returns. The signature saved at its previous access is the key.
            train_signature(record.signature, gap);
            recent_gaps_.push_back(gap);
            if (recent_gaps_.size() > 64) recent_gaps_.pop_front();
            record.gap = record.repeated ? 0.5 * record.gap + 0.5 * gap : gap;
            record.frequency = record.frequency * std::exp2(-gap / decay_scale_) + 1;
            record.last = now;
            record.repeated = true;
            order_.splice(order_.end(), order_, record.position);
        }
        auto& updated = records_.at(page);
        updated.signature = current_signature;
        updated.signature_gap = std::numeric_limits<double>::infinity();
        if (current_signature) {
            const auto learned = signatures_.find(*current_signature);
            if (learned != signatures_.end()) updated.signature_gap = learned->second.gap;
        }
        if (!updated.repeated && recent_gaps_.size() >= 8) {
            std::vector<double> samples(recent_gaps_.begin(), recent_gaps_.end());
            auto quartile = samples.begin() + static_cast<std::ptrdiff_t>(samples.size() / 4);
            std::nth_element(samples.begin(), quartile, samples.end());
            updated.cold_gap = *quartile;
        }
        if (tape_.size() == tape_limit_) {
            auto entry = positions_.find(tape_.front());
            entry->second.pop_front();
            if (entry->second.empty()) positions_.erase(entry);
            tape_.pop_front();
            ++base_;
        }
        tape_.push_back(page);
        positions_[page].push_back(now);
    }
};

class Cache {
    struct Entry { Page page; std::size_t last; };
    std::size_t capacity_;
    std::vector<Entry> frames_;
    std::unordered_map<Page, std::size_t> resident_;
    std::mt19937_64 random_;
    std::size_t random_slot(std::size_t count) {
        const auto bound = static_cast<std::uint64_t>(count);
        const auto threshold = (std::uint64_t{0} - bound) % bound;
        std::uint64_t draw;
        do { draw = random_(); } while (draw < threshold);
        return static_cast<std::size_t>(draw % bound);
    }
public:
    Cache(std::size_t capacity, std::uint64_t seed) : capacity_(capacity), random_(seed) {}
    bool contains(Page page) const { return resident_.count(page) != 0; }

    Event access(Page page, std::size_t now, std::size_t policy,
                 const Observations& observations, const Cache* target = nullptr) {
        const auto found = resident_.find(page);
        if (found != resident_.end()) {
            frames_[found->second].last = now;
            return {now + 1, page, true, found->second, {}};
        }
        std::size_t slot = frames_.size();
        std::optional<Page> evicted;
        if (frames_.size() < capacity_) {
            frames_.push_back({page, now});
        } else {
            // Follow a shadow by *evicting* an actual page it does not need.
            // Never copy in a shadow page. Since target already holds the
            // requested page, at least one eligible actual victim exists.
            std::vector<std::size_t> eligible;
            for (std::size_t j = 0; j < frames_.size(); ++j) {
                if (!target || !target->contains(frames_[j].page)) eligible.push_back(j);
            }
            if (eligible.empty()) throw std::logic_error("no legal reconciliation victim");
            slot = eligible[0];
            if (policy == 0) slot = eligible[random_slot(eligible.size())];
            else {
                double best = policy == 1 ? 0 : observations.score(frames_[slot].page, now, policy);
                for (const auto j : eligible) {
                    const double score = policy == 1 ? 0 : observations.score(frames_[j].page, now, policy);
                    if (score > best || (score == best && frames_[j].last < frames_[slot].last)) {
                        slot = j;
                        best = score;
                    }
                }
            }
            evicted = frames_[slot].page;
            resident_.erase(*evicted);
            frames_[slot] = {page, now};
        }
        resident_[page] = slot;
        return {now + 1, page, false, slot, evicted};
    }
};
} // namespace

struct OnlineAdaptiveV5::Impl {
    const std::size_t window, check_interval;
    const double margin, decay;
    Observations observations;
    Cache actual;
    std::vector<Cache> shadows;
    std::array<double, expert_count> losses{};
    std::size_t selected = 15;
    Result statistics;
    LearnedDiagnostics diagnostics;

    Impl(std::size_t capacity, std::uint64_t seed, AdaptiveOptions options)
        : window(std::max(std::size_t{32}, product(product(capacity, options.window_factor), 2))),
          check_interval(std::max(std::size_t{1}, window / 8)),
          margin(std::max(1.0, static_cast<double>(window) / 20)),
          decay(1.0 - 1.0 / static_cast<double>(window)),
          observations(capacity, capacity > 20 ? std::max(std::size_t{1}, options.history_factor / 2) : options.history_factor),
          actual(capacity, seed) {
        for (std::size_t j = 0; j < expert_count; ++j) shadows.emplace_back(capacity, seed);
    }
    Event access(Page page) {
        const auto now = statistics.references;
        if (now == std::numeric_limits<std::size_t>::max()) throw std::overflow_error("reference count overflow");
        // Select using losses of completed requests, then advance every shadow.
        if (now >= 32 && now % check_interval == 0) {
            auto best = selected;
            for (std::size_t j = 0; j < expert_count; ++j) if (losses[j] < losses[best]) best = j;
            if (losses[selected] - losses[best] > margin) { selected = best; ++statistics.policy_switches; }
        }
        observations.prepare(page, now);
        if (observations.predicts()) ++statistics.context_predictions;
        for (std::size_t j = 0; j < expert_count; ++j) {
            const auto miss = shadows[j].access(page, now, j, observations).hit ? 0U : 1U;
            losses[j] = losses[j] * decay + miss;
            diagnostics.expert_faults[j] += miss;
            if (j < statistics.expert_faults.size()) statistics.expert_faults[j] += miss;
        }
        const auto event = actual.access(page, now, selected, observations, &shadows[selected]);
        ++statistics.references;
        ++diagnostics.expert_uses[selected];
        if (selected < statistics.expert_uses.size()) ++statistics.expert_uses[selected];
        ++statistics.policy_uses[std::min(std::size_t{2}, selected)];
        if (event.hit) ++statistics.hits; else ++statistics.faults;
        if (event.evicted) ++statistics.evictions;
        // A completed reuse gap becomes a label only here, after this decision.
        observations.observe(page, now);
        statistics.history_peak = std::max(statistics.history_peak, observations.size());
        statistics.context_history_peak = std::max(statistics.context_history_peak, observations.tape_size());
        statistics.signature_history_peak = std::max(statistics.signature_history_peak, observations.signature_size());
        diagnostics.model_peak = std::max(diagnostics.model_peak, observations.model_size());
        return event;
    }
};
OnlineAdaptiveV5::OnlineAdaptiveV5(std::size_t capacity, std::uint64_t seed, AdaptiveOptions options) {
    if (options.version != 5) throw std::invalid_argument("OnlineAdaptiveV5 requires adaptive version 5");
    limit(capacity, options.history_factor);
    limit(capacity, options.window_factor);
    impl_ = std::make_unique<Impl>(capacity, seed, options);
}
OnlineAdaptiveV5::~OnlineAdaptiveV5() = default;
OnlineAdaptiveV5::OnlineAdaptiveV5(OnlineAdaptiveV5&&) noexcept = default;
OnlineAdaptiveV5& OnlineAdaptiveV5::operator=(OnlineAdaptiveV5&&) noexcept = default;
Event OnlineAdaptiveV5::access(Page page) { return impl_->access(page); }
const Result& OnlineAdaptiveV5::result() const { return impl_->statistics; }
const LearnedDiagnostics& OnlineAdaptiveV5::diagnostics() const { return impl_->diagnostics; }
Result simulate_v5(const std::vector<Page>& trace, std::size_t capacity, std::uint64_t seed,
                   bool record_events, AdaptiveOptions options) {
    OnlineAdaptiveV5 engine(capacity, seed, options);
    std::vector<Event> events;
    if (record_events) events.reserve(trace.size());
    for (const auto page : trace) {
        const auto event = engine.access(page);
        if (record_events) events.push_back(event);
    }
    auto result = engine.result();
    result.events = std::move(events);
    return result;
}
} // namespace paging
