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
  const [boardAttachment, setBoardAttachment] = useState(
    runtimeControl?.board ?? {
      attached: false,
      transport: null,
      port: null,
      target: null,
      preferred_transport: null,
    },
  );
  const [selectedBoardTransport, setSelectedBoardTransport] = useState<string | null>(
    runtimeControl?.board.transport ?? runtimeControl?.board.preferred_transport ?? null,
  );
  const [selectedBoardPort, setSelectedBoardPort] = useState<string | null>(
    runtimeControl?.board.port ?? null,
  );

  useEffect(() => {
    setSelectedPane(operatorConsole?.panes[0] ?? "control_plane");
  }, [operatorConsole]);

  useEffect(() => {
    setSelectedAdapterName(runtimeControl?.active_adapter ?? runtimeAdapters[0]?.name ?? null);
    setSelectedModuleName(runtimeControl?.module_focus ?? runtimeModules[0]?.name ?? null);
    setBoardAttachment(
      runtimeControl?.board ?? {
        attached: false,
        transport: null,
        port: null,
        target: null,
        preferred_transport: null,
      },
    );
    setSelectedBoardTransport(
      runtimeControl?.board.transport ?? runtimeControl?.board.preferred_transport ?? null,
    );
    setSelectedBoardPort(runtimeControl?.board.port ?? null);
  }, [runtimeAdapters, runtimeControl, runtimeModules]);

  const cycleAdapter = async () => {
    if (!runtimeAdapters.length) return;
    const currentIndex = runtimeAdapters.findIndex((adapter) => adapter.name === selectedAdapterName);
    const nextIndex = currentIndex >= 0 ? (currentIndex + 1) % runtimeAdapters.length : 0;
    const nextAdapter = runtimeAdapters[nextIndex]?.name ?? runtimeAdapters[0]?.name ?? null;
    if (!nextAdapter) return;
    const payload = await controlKernel(token, "switch_adapter", { adapter: nextAdapter });
    onKernelUpdate(payload.kernel);
  };

  const attachBoard = async ({
    transport,
    port,
  }: {
    transport?: string | null;
    port?: string | null;
  } = {}) => {
    const payload = await controlKernel(token, "attach_board", {
      transport: transport ?? selectedBoardTransport ?? undefined,
      port: port ?? selectedBoardPort ?? undefined,
    });
    onKernelUpdate(payload.kernel);
    setSelectedPane("adapters");
  };

  const detachBoard = async () => {
    const payload = await controlKernel(token, "detach_board");
    onKernelUpdate(payload.kernel);
    setSelectedPane("adapters");
  };

  const focusModule = async (moduleName: string | null) => {
    if (!moduleName) return;
    const payload = await controlKernel(token, "focus_module", { module: moduleName });
    onKernelUpdate(payload.kernel);
  };

  const clearFault = async (adapterName: string | null = null) => {
    const payload = await controlKernel(token, "clear_fault", {
      adapter: adapterName ?? selectedAdapterName ?? undefined,
    });
    onKernelUpdate(payload.kernel);
    setSelectedPane("faults");
  };

  const recordFault = async (
    level: string = "fault",
    adapterName: string | null = null,
  ) => {
    const payload = await controlKernel(token, "record_fault", {
      level,
      adapter: adapterName ?? selectedAdapterName ?? undefined,
    });
    onKernelUpdate(payload.kernel);
    setSelectedPane("faults");
  };

  const restartBridge = async (adapterName: string | null = null) => {
    const payload = await controlKernel(token, "restart_bridge", {
      adapter: adapterName ?? selectedAdapterName ?? undefined,
    });
    onKernelUpdate(payload.kernel);
    setSelectedPane("adapters");
  };

  const pauseRuntime = async () => {
    const payload = await controlKernel(token, "pause_runtime");
    onKernelUpdate(payload.kernel);
    setSelectedPane("runtime");
  };

  const resumeRuntime = async () => {
    const payload = await controlKernel(token, "resume_runtime");
    onKernelUpdate(payload.kernel);
    setSelectedPane("runtime");
  };

  const degradeRuntime = async () => {
    const payload = await controlKernel(token, "degrade_runtime");
    onKernelUpdate(payload.kernel);
    setSelectedPane("runtime");
  };

  const drainBackground = async () => {
    const payload = await controlKernel(token, "drain_background");
    onKernelUpdate(payload.kernel);
    setSelectedPane("runtime");
  };

  const prioritizeGoalLane = async () => {
    const payload = await controlKernel(token, "prioritize_goal_lane");
    onKernelUpdate(payload.kernel);
    setSelectedPane("runtime");
  };

  const enterMaintenance = async () => {
    const payload = await controlKernel(token, "enter_maintenance");
    onKernelUpdate(payload.kernel);
    setSelectedPane("control_plane");
  };

  const exitMaintenance = async () => {
    const payload = await controlKernel(token, "exit_maintenance");
    onKernelUpdate(payload.kernel);
    setSelectedPane("control_plane");
  };

  return useMemo(
    () => ({
      selectedPane,
      setSelectedPane,
      selectedAdapterName,
      setSelectedAdapterName,
      selectedModuleName,
      setSelectedModuleName,
      boardAttachment,
      selectedBoardTransport,
      setSelectedBoardTransport,
      selectedBoardPort,
      setSelectedBoardPort,
      cycleAdapter,
      attachBoard,
      detachBoard,
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
      boardAttachment,
      selectedBoardTransport,
      selectedBoardPort,
      token,
      onKernelUpdate,
    ],
  );
}
