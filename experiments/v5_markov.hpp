#pragma once
#include <array>
#include <deque>
#include <list>
#include <unordered_map>
#include <limits>

namespace paging {
class MarkovForecast {
    struct Key {
        std::array<Page,4> pages{};
        unsigned length=0;
        bool operator==(const Key& other) const { return length==other.length && pages==other.pages; }
    };
    struct Hash {
        std::size_t operator()(const Key& key) const {
            std::size_t h=key.length;
            for(auto p:key.pages) h^=std::hash<Page>{}(p)+0x9e3779b97f4a7c15ULL+(h<<6)+(h>>2);
            return h;
        }
    };
    struct Node {
        std::array<Page,4> next{};
        std::array<unsigned,4> counts{};
        Page latest=0;
        std::list<Key>::iterator position;
    };
    std::size_t limit_, horizon_;
    std::deque<Page> suffix_;
    std::list<Key> order_;
    std::unordered_map<Key,Node,Hash> nodes_;
    std::array<std::unordered_map<Page,std::size_t>,2> forecasts_;
    std::array<std::size_t,2> spans_{};
    Key key(const std::deque<Page>& suffix,unsigned n) const {
        Key out; out.length=n;
        for(unsigned i=0;i<n;++i) out.pages[i]=suffix[suffix.size()-1-i];
        return out;
    }
public:
    explicit MarkovForecast(std::size_t capacity):limit_(std::max(std::size_t{128},capacity*64)),horizon_(std::max(std::size_t{32},capacity*8)) {}
    void prepare(Page current) {
        for(unsigned mode=0;mode<2;++mode) {
            forecasts_[mode].clear(); spans_[mode]=0;
            auto suffix=suffix_; suffix.push_back(current); if(suffix.size()>4) suffix.pop_front();
            for(std::size_t distance=1;distance<=horizon_;++distance) {
                bool found=false; Page prediction=0;
                for(unsigned n=static_cast<unsigned>(suffix.size());n>0;--n) {
                    auto it=nodes_.find(key(suffix,n)); if(it==nodes_.end()) continue;
                    const auto& node=it->second;
                    if(!mode) { prediction=node.latest; found=true; break; }
                    auto best=0U, total=0U;
                    for(unsigned j=0;j<4;++j) { total+=node.counts[j]; if(node.counts[j]>node.counts[best]) best=j; }
                    if(node.counts[best]>=2 && node.counts[best]*2>=total) { prediction=node.next[best]; found=true; break; }
                }
                if(!found) break;
                forecasts_[mode].emplace(prediction,distance); spans_[mode]=distance;
                suffix.push_back(prediction); if(suffix.size()>4) suffix.pop_front();
            }
        }
    }
    double score(Page page,double fallback,std::size_t policy) const {
        const auto mode=policy/2;
        if(!spans_[mode]) return fallback;
        auto it=forecasts_[mode].find(page);
        if(it!=forecasts_[mode].end()) return static_cast<double>(it->second);
        if(policy%2) return static_cast<double>(spans_[mode])+fallback;
        return std::max(static_cast<double>(spans_[mode]+1),fallback);
    }
    void observe(Page page) {
        for(unsigned n=1;n<=suffix_.size();++n) {
            const auto k=key(suffix_,n);
            auto it=nodes_.find(k);
            if(it==nodes_.end()) {
                if(nodes_.size()==limit_) { nodes_.erase(order_.front()); order_.pop_front(); }
                order_.push_back(k); Node node; node.position=std::prev(order_.end());
                it=nodes_.emplace(k,node).first;
            } else order_.splice(order_.end(),order_,it->second.position);
            auto& node=it->second; node.latest=page;
            unsigned slot=0; bool found=false;
            for(unsigned j=0;j<4;++j) if(node.counts[j] && node.next[j]==page) { slot=j; found=true; break; }
            if(!found) {
                for(unsigned j=1;j<4;++j) if(node.counts[j]<node.counts[slot]) slot=j;
                node.next[slot]=page; node.counts[slot]=0;
            }
            if(node.counts[slot]>=64) for(auto& count:node.counts) count=(count+1)/2;
            ++node.counts[slot];
        }
        suffix_.push_back(page); if(suffix_.size()>4) suffix_.pop_front();
    }
};
}
