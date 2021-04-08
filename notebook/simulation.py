import random


def argmax(a):
    return max(range(len(a)), key=lambda x: a[x])


print("Thompson sampling demo")
print("Goal is to maximize payout from three machines")
print("Machines pay out with probs 0.3, 0.7, 0.5")

N = 3  # number machines
means = [0.3, 0.7, 0.5]
probs = [0] * N
S = [0] * N
F = [0] * N

for trial in range(10):
    print("\nTrial " + str(trial))
    for i in range(N):
        probs[i] = random.betavariate(S[i] + 1, F[i] + 1)

    print("sampling probs =  ", end="")
    for i in range(N):
        print("%0.4f  " % probs[i], end="")
    print("")

    machine = argmax(probs)
    print("Playing machine " + str(machine), end="")

    p = random.uniform(0, 1)
    if p < means[machine]:
        print(" -- win")
        S[machine] += 1
    else:
        print(" -- lose")
        F[machine] += 1

print("Final Success vector: ", end="")
print(S)
print("Final Failure vector: ", end="")
print(F)
