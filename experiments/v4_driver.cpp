#include "paging.hpp"
#include <fstream>
#include <iostream>
#include <string>
int main(int argc, char** argv) {
  for (int a=1;a<argc;++a) {
    std::ifstream in(argv[a]); auto trace=paging::read_trace(in);
    for (const auto f : {5U,10U,20U,50U,100U}) {
      auto r=paging::simulate(trace,f,paging::Algorithm::Adaptive,0,false,{4,16,4});
      std::cout << argv[a] << ',' << f << ',' << r.faults << ',' << r.policy_switches;
      for(auto n:r.expert_faults) std::cout << ',' << n;
      for(auto n:r.expert_uses) std::cout << ',' << n;
      std::cout << '\n';
    }
  }
}
