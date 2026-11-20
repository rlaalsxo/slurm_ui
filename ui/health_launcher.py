"""[Health 창 열기] — Node Health(Qt)를 별도 프로세스로 띄운다(Tk 와 Qt 는 한 프로세스에 못 섞는다)."""
import subprocess

from runtime import app_dir, health_command, health_environment


def launch_health():
    """띄우기만 하고 기다리지 않는다. slurm_ui 를 닫아도 Health 창은 남는다. 실패하면 OSError."""
    subprocess.Popen(health_command(), env=health_environment(), cwd=str(app_dir()), close_fds=True)
