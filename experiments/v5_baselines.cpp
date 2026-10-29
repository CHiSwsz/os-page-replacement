// Independent research baselines for equal-sized, mandatory-admission pages.
// ARC: Megiddo & Modha, FAST 2003.
// S3-FIFO: Yang et al., SOSP 2023; stop after the first physical eviction,
// preserving the assignment's one-page-in/one-page-out demand-paging model.
// SIEVE: Zhang et al., NSDI 2024.
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <deque>
#include <fstream>
#include <iostream>
#include <list>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
using Page=std::uint64_t;
struct Queue {
    std::list<Page> order;
    std::unordered_map<Page,std::list<Page>::iterator> positions;
    bool has(Page p) const { return positions.count(p)!=0; }
    std::size_t size() const { return order.size(); }
    bool empty() const { return order.empty(); }
    void erase(Page p) { auto it=positions.find(p); assert(it!=positions.end()); order.erase(it->second); positions.erase(it); }
    void push(Page p) { assert(!has(p)); order.push_back(p); positions[p]=std::prev(order.end()); }
    Page pop() { assert(!empty()); auto p=order.front(); erase(p); return p; }
};
struct ARC {
    std::size_t capacity;
    double target=0;
    Queue t1,t2,b1,b2;
    explicit ARC(std::size_t c):capacity(c) {}
    bool contains(Page p) const { return t1.has(p)||t2.has(p); }
    std::set<Page> resident() const {
        std::set<Page> out(t1.order.begin(),t1.order.end()); out.insert(t2.order.begin(),t2.order.end()); return out;
    }
    void replace(bool in_b2) {
        if(!t1.empty() && (t1.size()>target || (in_b2 && t1.size()==target))) b1.push(t1.pop());
        else b2.push(t2.pop());
    }
    bool access(Page p) {
        if(t1.has(p)) { t1.erase(p); t2.push(p); return true; }
        if(t2.has(p)) { t2.erase(p); t2.push(p); return true; }
        if(b1.has(p)) {
            target=std::min(static_cast<double>(capacity),target+std::max(1.0,static_cast<double>(b2.size())/b1.size()));
            replace(false); b1.erase(p); t2.push(p);
        } else if(b2.has(p)) {
            target=std::max(0.0,target-std::max(1.0,static_cast<double>(b1.size())/b2.size()));
            replace(true); b2.erase(p); t2.push(p);
        } else {
            if(t1.size()+b1.size()==capacity) {
                if(t1.size()<capacity) { b1.pop(); replace(false); }
                else t1.pop();
            } else if(t1.size()+t2.size()+b1.size()+b2.size()>=capacity) {
                if(t1.size()+t2.size()+b1.size()+b2.size()==2*capacity) b2.pop();
                replace(false);
            }
            t1.push(p);
        }
        assert(t1.size()+t2.size()<=capacity);
        assert(t1.size()+t2.size()+b1.size()+b2.size()<=2*capacity);
        return false;
    }
};
struct S3FIFO {
    std::size_t capacity, small_target, main_target;
    std::deque<Page> small, main;
    Queue ghost;
    std::unordered_map<Page,unsigned> frequency;
    explicit S3FIFO(std::size_t c):capacity(c),small_target(std::max(std::size_t{1},c/10)),main_target(std::max(std::size_t{1},c-small_target)) {}
    bool contains(Page p) const { return frequency.count(p)!=0; }
    std::set<Page> resident() const { std::set<Page> out; for(auto x:frequency) out.insert(x.first); return out; }
    void evict_main() {
        while(!main.empty()) {
            auto p=main.front(); main.pop_front();
            if(frequency.at(p)) { --frequency.at(p); main.push_back(p); }
            else { frequency.erase(p); return; }
        }
        throw std::logic_error("empty main queue");
    }
    void evict() {
        if(small.size()>=small_target || main.empty()) {
            while(!small.empty()) {
                auto p=small.front(); small.pop_front();
                if(frequency.at(p)>1) {
                    frequency.at(p)=0; main.push_back(p);
                    if(main.size()>=main_target) { evict_main(); return; }
                } else {
                    frequency.erase(p);
                    if(ghost.has(p)) ghost.erase(p);
                    if(ghost.size()==main_target) ghost.pop();
                    ghost.push(p); return;
                }
            }
        }
        evict_main();
    }
    bool access(Page p) {
        auto it=frequency.find(p);
        if(it!=frequency.end()) { it->second=std::min(3U,it->second+1); return true; }
        if(frequency.size()==capacity) evict();
        if(ghost.has(p)) { ghost.erase(p); main.push_back(p); }
        else small.push_back(p);
        frequency[p]=0;
        assert(frequency.size()<=capacity);
        return false;
    }
};
struct SIEVE {
    struct Entry { bool visited; std::list<Page>::iterator position; };
    std::size_t capacity;
    std::list<Page> order;
    std::list<Page>::iterator hand;
    std::unordered_map<Page,Entry> entries;
    explicit SIEVE(std::size_t c):capacity(c),hand(order.end()) {}
    bool contains(Page p) const { return entries.count(p)!=0; }
    std::set<Page> resident() const { return {order.begin(),order.end()}; }
    void advance() { if(hand==order.begin()) hand=order.end(); else --hand; }
    bool access(Page p) {
        auto it=entries.find(p);
        if(it!=entries.end()) { it->second.visited=true; return true; }
        if(entries.size()==capacity) {
            for(;;) {
                if(hand==order.end()) hand=std::prev(order.end());
                if(!entries.at(*hand).visited) break;
                entries.at(*hand).visited=false; advance();
            }
            auto victim=hand; advance();
            entries.erase(*victim); order.erase(victim);
        }
        order.push_front(p); entries.emplace(p,Entry{false,order.begin()});
        return false;
    }
};
template<class Policy>
std::size_t run(const std::vector<Page>& trace,std::size_t capacity,bool verify=false) {
    Policy policy(capacity);
    std::set<Page> seen;
    std::size_t faults=0;
    for(auto page:trace) {
        const auto before=verify?policy.resident():std::set<Page>{};
        const bool expected_hit=policy.contains(page), hit=policy.access(page);
        if(hit!=expected_hit) throw std::logic_error("incorrect hit accounting");
        faults+=!hit;
        if(verify) {
            seen.insert(page);
            auto after=policy.resident();
            assert(after.count(page));
            assert(after.size()==std::min(capacity,seen.size()));
            for(auto p:after) assert(p==page || before.count(p));
            std::size_t removed=0; for(auto p:before) removed+=!after.count(p);
            assert(removed==(hit||before.size()<capacity?0:1));
        }
    }
    return faults;
}
void self_test() {
    std::size_t cases=0;
    for(std::size_t length=0,power=1;length<=8;++length,power*=3)
      for(std::size_t word=0;word<power;++word) {
        std::vector<Page> trace; auto n=word;
        for(std::size_t i=0;i<length;++i) { trace.push_back(n%3); n/=3; }
        for(auto f:{1U,2U,3U,4U}) {
            run<ARC>(trace,f,true); run<S3FIFO>(trace,f,true); run<SIEVE>(trace,f,true); ++cases;
        }
      }
    std::cout<<"Legal demand-paging checks passed: "<<cases<<" traces/capacities, three policies.\n";
}
int main(int argc,char** argv) {
    if(argc==2 && std::string(argv[1])=="--self-test") { self_test(); return 0; }
    std::cout<<"dataset,frames,algorithm,faults\n";
    for(int a=1;a<argc;++a) {
        std::ifstream in(argv[a]); if(!in) return 2;
        std::vector<Page> trace; std::string line;
        while(std::getline(in,line)) if(!line.empty()) trace.push_back(std::stoull(line,nullptr,16));
        for(auto c:{5U,10U,20U,50U,100U}) {
            std::cout<<argv[a]<<','<<c<<",arc,"<<run<ARC>(trace,c)<<'\n';
            std::cout<<argv[a]<<','<<c<<",s3fifo_demand,"<<run<S3FIFO>(trace,c)<<'\n';
            std::cout<<argv[a]<<','<<c<<",sieve,"<<run<SIEVE>(trace,c)<<'\n';
        }
    }
}
