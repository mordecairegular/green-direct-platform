"""Tkinter GUI for the standalone batch trial tool."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from green_direct.io.validators import DataValidationError
from green_direct.models.params import BessParams, PolicyParams
from green_direct.services.batch_trial_runner import (
    BatchTrialRunConfig,
    default_scenario_grid,
    estimate_trial_scenario_count,
    run_batch_trial,
)


def application_dir() -> Path:
    """Directory where user-facing outputs should be created."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def bundled_resource_dir() -> Path:
    """Directory containing PyInstaller-bundled data such as samples/docs."""

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path.cwd()


class BatchTrialApp(ttk.Frame):
    """Small desktop wrapper around the existing batch simulator."""

    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=12)
        self.master = master
        self.master.title("绿电直连方案遍历试用程序")
        self.master.minsize(760, 620)
        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        output_default = application_dir() / "outputs"
        self.vars = {
            "load_csv": tk.StringVar(),
            "pv_csv": tk.StringVar(),
            "wind_csv": tk.StringVar(),
            "output_dir": tk.StringVar(value=str(output_default)),
            "pv_start": tk.StringVar(value="0"),
            "pv_end": tk.StringVar(value="30"),
            "pv_step": tk.StringVar(value="5"),
            "wind_start": tk.StringVar(value="0"),
            "wind_end": tk.StringVar(value="30"),
            "wind_step": tk.StringVar(value="5"),
            "bess_power_start": tk.StringVar(value="0"),
            "bess_power_end": tk.StringVar(value="10"),
            "bess_power_step": tk.StringVar(value="2"),
            "bess_durations": tk.StringVar(value="0,2,4"),
            "soc_initial": tk.StringVar(value="0.5"),
            "soc_min": tk.StringVar(value="0.1"),
            "soc_max": tk.StringVar(value="0.9"),
            "eta_charge": tk.StringVar(value="0.95"),
            "eta_discharge": tk.StringVar(value="0.95"),
            "cycle_life": tk.StringVar(value="6000"),
            "allow_export": tk.BooleanVar(value=True),
            "enforce_export_cap": tk.BooleanVar(value=True),
            "self_use_rate_min": tk.StringVar(value="0.60"),
            "green_load_rate_min": tk.StringVar(value="0.30"),
            "export_rate_max": tk.StringVar(value="0.20"),
            "grid_exchange_power_limit": tk.StringVar(value=""),
            "warn_if_scenarios_exceed": tk.StringVar(value="5000"),
        }

        self.status_var = tk.StringVar(value="请选择三条 CSV 曲线后开始测算。")
        self.progress_var = tk.DoubleVar(value=0)
        self._build_form()

    def _build_form(self) -> None:
        row = 0
        title = ttk.Label(self, text="方案遍历 + 方案概览/详表导出", font=("", 14, "bold"))
        title.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
        row += 1

        row = self._file_row(row, "负荷 CSV", "load_csv")
        row = self._file_row(row, "光伏 CSV", "pv_csv")
        row = self._file_row(row, "风电 CSV", "wind_csv")
        row = self._directory_row(row, "输出文件夹", "output_dir")

        row = self._section(row, "容量搜索范围（单位：万千瓦；储能时长单位：小时）")
        row = self._triple_row(row, "光伏容量 起/止/步长", "pv_start", "pv_end", "pv_step")
        row = self._triple_row(row, "风电容量 起/止/步长", "wind_start", "wind_end", "wind_step")
        row = self._triple_row(row, "储能功率 起/止/步长", "bess_power_start", "bess_power_end", "bess_power_step")
        row = self._single_row(row, "储能时长选项", "bess_durations")

        row = self._section(row, "储能参数")
        row = self._triple_row(row, "SOC 初始/下限/上限", "soc_initial", "soc_min", "soc_max")
        row = self._triple_row(row, "充电效率/放电效率/循环寿命", "eta_charge", "eta_discharge", "cycle_life")

        row = self._section(row, "政策约束")
        row = self._checkbox_row(row)
        row = self._triple_row(row, "自发自用率/绿电占比/上网比例", "self_use_rate_min", "green_load_rate_min", "export_rate_max")
        row = self._single_row(row, "电网交换功率限制（空白表示不限制）", "grid_exchange_power_limit")
        row = self._single_row(row, "方案数提醒阈值", "warn_if_scenarios_exceed")

        button_frame = ttk.Frame(self)
        button_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(12, 4))
        ttk.Button(button_frame, text="预估方案数", command=self._estimate).pack(side="left")
        self.run_button = ttk.Button(button_frame, text="开始测算并导出", command=self._start_run)
        self.run_button.pack(side="left", padx=(8, 0))
        ttk.Button(button_frame, text="填入示例数据路径", command=self._use_sample_paths).pack(side="left", padx=(8, 0))
        row += 1

        ttk.Progressbar(self, variable=self.progress_var, maximum=100).grid(row=row, column=0, columnspan=3, sticky="ew")
        row += 1
        ttk.Label(self, textvariable=self.status_var).grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 4))
        row += 1

        self.log = tk.Text(self, height=8, wrap="word")
        self.log.grid(row=row, column=0, columnspan=3, sticky="nsew")
        self.rowconfigure(row, weight=1)

    def _file_row(self, row: int, label: str, key: str) -> int:
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(self, textvariable=self.vars[key]).grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(self, text="浏览", command=lambda: self._browse_file(key)).grid(row=row, column=2, pady=2)
        return row + 1

    def _directory_row(self, row: int, label: str, key: str) -> int:
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(self, textvariable=self.vars[key]).grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(self, text="选择", command=lambda: self._browse_dir(key)).grid(row=row, column=2, pady=2)
        return row + 1

    def _section(self, row: int, label: str) -> int:
        ttk.Label(self, text=label, font=("", 10, "bold")).grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 2))
        return row + 1

    def _triple_row(self, row: int, label: str, first: str, second: str, third: str) -> int:
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=2)
        frame = ttk.Frame(self)
        frame.grid(row=row, column=1, columnspan=2, sticky="ew", pady=2)
        for column, key in enumerate([first, second, third]):
            frame.columnconfigure(column, weight=1)
            ttk.Entry(frame, textvariable=self.vars[key], width=10).grid(row=0, column=column, sticky="ew", padx=(0, 4))
        return row + 1

    def _single_row(self, row: int, label: str, key: str) -> int:
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(self, textvariable=self.vars[key]).grid(row=row, column=1, columnspan=2, sticky="ew", padx=4, pady=2)
        return row + 1

    def _checkbox_row(self, row: int) -> int:
        frame = ttk.Frame(self)
        frame.grid(row=row, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Checkbutton(frame, text="允许上网", variable=self.vars["allow_export"]).pack(side="left")
        ttk.Checkbutton(frame, text="启用年度上网比例硬约束", variable=self.vars["enforce_export_cap"]).pack(side="left", padx=(16, 0))
        return row + 1

    def _browse_file(self, key: str) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.vars[key].set(path)

    def _browse_dir(self, key: str) -> None:
        path = filedialog.askdirectory()
        if path:
            self.vars[key].set(path)

    def _use_sample_paths(self) -> None:
        sample_dir = bundled_resource_dir() / "samples"
        self.vars["load_csv"].set(str(sample_dir / "负荷系数示例文件.csv"))
        self.vars["pv_csv"].set(str(sample_dir / "光伏系数示例文件-1300.csv"))
        self.vars["wind_csv"].set(str(sample_dir / "风电系数示例文件.csv"))
        self.vars["pv_start"].set("10")
        self.vars["pv_end"].set("20")
        self.vars["pv_step"].set("10")
        self.vars["wind_start"].set("5")
        self.vars["wind_end"].set("15")
        self.vars["wind_step"].set("10")
        self.vars["bess_power_start"].set("0")
        self.vars["bess_power_end"].set("4")
        self.vars["bess_power_step"].set("2")
        self.vars["bess_durations"].set("0,2,4")
        self.status_var.set(f"已填入示例数据路径并切换为 20 个示例方案：{sample_dir}")

    def _estimate(self) -> None:
        try:
            count = estimate_trial_scenario_count(self._scenario_grid())
            self.status_var.set(f"当前容量范围预计生成 {count} 个候选方案。")
        except Exception as exc:  # noqa: BLE001 - GUI should keep errors friendly
            messagebox.showerror("方案范围有误", str(exc))

    def _start_run(self) -> None:
        try:
            config = self._config()
            self._validate_before_thread(config)
        except Exception as exc:  # noqa: BLE001 - GUI should keep errors friendly
            messagebox.showerror("参数有误", str(exc))
            return

        self.run_button.configure(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("开始测算...")
        self._log("开始测算。")
        threading.Thread(target=self._run_worker, args=(config,), daemon=True).start()

    def _run_worker(self, config: BatchTrialRunConfig) -> None:
        try:
            artifacts = run_batch_trial(config, progress_callback=self._on_progress)
        except (DataValidationError, FileNotFoundError, ValueError) as exc:
            self.master.after(0, lambda: self._fail(str(exc)))
        except Exception as exc:  # noqa: BLE001 - show unexpected errors instead of crashing
            self.master.after(0, lambda: self._fail(f"测算失败：{exc}"))
        else:
            self.master.after(0, lambda: self._finish(artifacts.run_dir))

    def _on_progress(self, done: int, total: int, scenario_id: str) -> None:
        percent = done / total * 100 if total else 100
        self.master.after(0, lambda: self._update_progress(percent, done, total, scenario_id))

    def _update_progress(self, percent: float, done: int, total: int, scenario_id: str) -> None:
        self.progress_var.set(percent)
        if total and done >= total:
            self.status_var.set(f"计算完成 {done}/{total}，正在导出 Excel 和逐小时 ZIP...")
        else:
            self.status_var.set(f"正在计算 {done}/{total}：{scenario_id}")

    def _finish(self, run_dir: Path) -> None:
        self.progress_var.set(100)
        self.run_button.configure(state="normal")
        self.status_var.set(f"测算完成，结果已输出到：{run_dir}")
        self._log(f"测算完成：{run_dir}")
        messagebox.showinfo("测算完成", f"结果已输出到：\n{run_dir}")
        if os.name == "nt":
            os.startfile(run_dir)  # noqa: S606 - user-selected local output folder

    def _fail(self, message: str) -> None:
        self.run_button.configure(state="normal")
        self.status_var.set(message)
        self._log(message)
        messagebox.showerror("测算失败", message)

    def _log(self, message: str) -> None:
        self.log.insert("end", message + "\n")
        self.log.see("end")

    def _validate_before_thread(self, config: BatchTrialRunConfig) -> None:
        missing = [
            path
            for path in [config.load_csv, config.pv_csv, config.wind_csv]
            if not Path(path).exists()
        ]
        if missing:
            names = "\n".join(str(path) for path in missing)
            raise FileNotFoundError(f"找不到输入文件，请重新选择 CSV：\n{names}")
        count = estimate_trial_scenario_count(config.scenario_grid)
        if count == 0:
            raise ValueError("当前容量范围没有可用候选方案，请至少设置光伏或风电容量。")
        if count > config.warn_if_scenarios_exceed:
            self._log(f"提示：当前预计生成 {count} 个方案，计算和导出可能需要一段时间。")

    def _config(self) -> BatchTrialRunConfig:
        return BatchTrialRunConfig(
            load_csv=Path(self.vars["load_csv"].get()),
            pv_csv=Path(self.vars["pv_csv"].get()),
            wind_csv=Path(self.vars["wind_csv"].get()),
            output_dir=Path(self.vars["output_dir"].get()),
            scenario_grid=self._scenario_grid(),
            bess_params=BessParams(
                soc_initial=self._float("soc_initial"),
                soc_min=self._float("soc_min"),
                soc_max=self._float("soc_max"),
                eta_charge=self._float("eta_charge"),
                eta_discharge=self._float("eta_discharge"),
                cycle_life=self._float("cycle_life"),
            ),
            policy_params=PolicyParams(
                self_use_rate_min=self._float("self_use_rate_min"),
                green_load_rate_min=self._float("green_load_rate_min"),
                export_rate_max=self._float("export_rate_max"),
                allow_export=bool(self.vars["allow_export"].get()),
                grid_exchange_power_limit=self._optional_float("grid_exchange_power_limit"),
                export_control_mode="annual_cap_runtime"
                if self.vars["enforce_export_cap"].get()
                else "post_check",
            ),
            warn_if_scenarios_exceed=int(self._float("warn_if_scenarios_exceed")),
        )

    def _scenario_grid(self) -> dict:
        grid = default_scenario_grid()
        grid["pv_capacity"] = {"start": self._float("pv_start"), "end": self._float("pv_end"), "step": self._float("pv_step")}
        grid["wind_capacity"] = {
            "start": self._float("wind_start"),
            "end": self._float("wind_end"),
            "step": self._float("wind_step"),
        }
        grid["bess_power"] = {
            "start": self._float("bess_power_start"),
            "end": self._float("bess_power_end"),
            "step": self._float("bess_power_step"),
        }
        durations = [
            float(part.strip())
            for part in self.vars["bess_durations"].get().replace("，", ",").split(",")
            if part.strip()
        ]
        grid["bess_duration_hours"] = durations
        return grid

    def _float(self, key: str) -> float:
        return float(self.vars[key].get().strip())

    def _optional_float(self, key: str) -> float | None:
        raw = self.vars[key].get().strip()
        return None if not raw else float(raw)


def main() -> None:
    root = tk.Tk()
    BatchTrialApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
