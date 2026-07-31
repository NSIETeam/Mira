import { useEffect, useMemo, useState } from "react";

import { controlKernel } from "@/lib/api";
import type { KernelManifestPayload } from "@/lib/types";

export function useKernelControlState({
  kernelManifest,
  token,
  onKernelUpdate,
}: {
  kernelManifest: KernelManifestPayload | null;
  token: string;
  onKernelUpdate: (kernel: KernelManifestPayload) => void;
}) {
  const runtimeControl = kernelManifest?.runtime_control ?? null;
  const runtimeAdapters = kernelManifest?.runtime_adapters ?? [];
  const operatorConsole = kernelManifest?.operator_console ?? null;
  const runtimeModules = kernelManifest?.runtime_modules ?? [];
  const [selectedPane, setSelectedPane] = useState<string>(
    operatorConsole?.panes[0] ?? "control_plane",
  );
  const [selectedAdapterName, setSelectedAdapterName] = useState<string | null>(
    runtimeControl?.active_adapter ?? runtimeAdapters[0]?.name ?? null,
  );
  const [selectedModuleName, setSelectedModuleName] = useState<string | null>(
    runtimeControl?.module_focus ?? runtimeModules[0]?.name ?? null,
  );

  useEffect(() => {
    setSelectedPane(operatorConsole?.panes[0] ?? "control_plane");
  }, [operatorConsole]);

  useEffect(() => {
    setSelectedAdapterName(runtimeControl?.active_adapter ?? runtimeAdapters[0]?.name ?? null);
    setSelectedModuleName(runtimeControl?.module_focus ?? runtimeModules[0]?.name ?? null);
  }, [runtimeAdapters, runtimeControl, runtimeModules]);

  const runControlAction = async (
    action: string,
    params: Record<string, string | undefined> = {},
    targetPane?: string,
  ) => {
    const payload = await controlKernel(token, action, params);
    onKernelUpdate(payload.kernel);
    if (targetPane) {
      setSelectedPane(targetPane);
    }
  };

  const cycleAdapter = async () => {
    if (!runtimeAdapters.length) return;
    const currentIndex = runtimeAdapters.findIndex((adapter) => adapter.name === selectedAdapterName);
    const nextIndex = currentIndex >= 0 ? (currentIndex + 1) % runtimeAdapters.length : 0;
    const nextAdapter = runtimeAdapters[nextIndex]?.name ?? runtimeAdapters[0]?.name ?? null;
    if (!nextAdapter) return;
    await runControlAction("switch_adapter", { adapter: nextAdapter });
  };

  const focusModule = async (moduleName: string | null) => {
    if (!moduleName) return;
    await runControlAction("focus_module", { module: moduleName });
  };

  const clearFault = async (adapterName: string | null = null) => {
    await runControlAction("clear_fault", {
      adapter: adapterName ?? selectedAdapterName ?? undefined,
    }, "faults");
  };

  const recordFault = async (
    level: string = "fault",
    adapterName: string | null = null,
  ) => {
    await runControlAction("record_fault", {
      level,
      adapter: adapterName ?? selectedAdapterName ?? undefined,
    }, "faults");
  };

  const restartBridge = async (adapterName: string | null = null) => {
    await runControlAction("restart_bridge", {
      adapter: adapterName ?? selectedAdapterName ?? undefined,
    }, "adapters");
  };

  const pauseRuntime = async () => {
    await runControlAction("pause_runtime", {}, "runtime");
  };

  const resumeRuntime = async () => {
    await runControlAction("resume_runtime", {}, "runtime");
  };

  const degradeRuntime = async () => {
    await runControlAction("degrade_runtime", {}, "runtime");
  };

  const drainBackground = async () => {
    await runControlAction("drain_background", {}, "runtime");
  };

  const prioritizeGoalLane = async () => {
    await runControlAction("prioritize_goal_lane", {}, "runtime");
  };

  const enterMaintenance = async () => {
    await runControlAction("enter_maintenance", {}, "control_plane");
  };

  const exitMaintenance = async () => {
    await runControlAction("exit_maintenance", {}, "control_plane");
  };

  return useMemo(
    () => ({
      selectedPane,
      setSelectedPane,
      selectedAdapterName,
      setSelectedAdapterName,
      selectedModuleName,
      setSelectedModuleName,
      cycleAdapter,
      focusModule,
      clearFault,
      recordFault,
      restartBridge,
      pauseRuntime,
      resumeRuntime,
      degradeRuntime,
      drainBackground,
      prioritizeGoalLane,
      enterMaintenance,
      exitMaintenance,
    }),
    [
      selectedPane,
      selectedAdapterName,
      selectedModuleName,
      token,
      onKernelUpdate,
    ],
  );
}
