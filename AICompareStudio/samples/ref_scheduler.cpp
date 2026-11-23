#include <vector>
#include "Task.hpp"

namespace os {

class Scheduler {
public:
    void addTask(Task* t) { tasks_.push_back(t); }
private:
    std::vector<Task*> tasks_;
};

int tickPeriodMs() { return 10; }

void Scheduler_Run(Scheduler& s, int cycles)
{
    for (int i = 0; i < cycles; ++i) {
        // run all tasks
    }
}

} // namespace os
