import subprocess
import sys

def main():
    subprocess.run([sys.executable, '-m', 'moex_bot.run_backtests'], check=False)
    subprocess.run([sys.executable, '-m', 'moex_bot.run_server'], check=False)

if __name__ == '__main__':
    main()
