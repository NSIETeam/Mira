import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";

import type { PairingRequestInfo, SessionAutomationJob } from "@/lib/types";

import { PairingCodePopup } from "./chrome";

const DeleteConfirm = lazy(async () => {
  const module = await import("@/components/DeleteConfirm");
  return { default: module.DeleteConfirm };
});

const RenameExecutionDialog = lazy(async () => {
  const module = await import("@/components/RenameExecutionDialog");
  return { default: module.RenameExecutionDialog };
});

export function EngineeringShellOverlays({
  pendingDelete,
  pendingRename,
  pendingProjectRename,
  restartToast,
  visiblePairingRequests,
  pairingBusyCode,
  pairingError,
  onCancelDelete,
  onConfirmDelete,
  onCancelRename,
  onConfirmRename,
  onCancelProjectRename,
  onConfirmProjectRename,
  onApprovePairing,
  onDismissPairing,
}: {
  pendingDelete: {
    key: string;
    label: string;
    automations?: SessionAutomationJob[];
  } | null;
  pendingRename: {
    key: string;
    label: string;
  } | null;
  pendingProjectRename: {
    key: string;
    label: string;
  } | null;
  restartToast: string | null;
  visiblePairingRequests: PairingRequestInfo[];
  pairingBusyCode: string | null;
  pairingError: string | null;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
  onCancelRename: () => void;
  onConfirmRename: (title: string) => void;
  onCancelProjectRename: () => void;
  onConfirmProjectRename: (title: string) => void;
  onApprovePairing: (code: string) => void;
  onDismissPairing: (code: string) => void;
}) {
  const { t } = useTranslation();

  return (
    <>
      {pendingDelete ? (
        <Suspense fallback={null}>
          <DeleteConfirm
            open
            title={pendingDelete.label}
            automations={pendingDelete.automations}
            onCancel={onCancelDelete}
            onConfirm={onConfirmDelete}
          />
        </Suspense>
      ) : null}
      {pendingRename ? (
        <Suspense fallback={null}>
          <RenameExecutionDialog
            open
            title={pendingRename.label}
            onCancel={onCancelRename}
            onConfirm={onConfirmRename}
          />
        </Suspense>
      ) : null}
      {pendingProjectRename ? (
        <Suspense fallback={null}>
          <RenameExecutionDialog
            open
            title={pendingProjectRename.label}
            dialogTitle={t("chat.renameProjectTitle")}
            description={t("chat.renameProjectDescription")}
            placeholder={t("chat.renameProjectPlaceholder")}
            onCancel={onCancelProjectRename}
            onConfirm={onConfirmProjectRename}
          />
        </Suspense>
      ) : null}
      {restartToast ? (
        <div
          role="status"
          className="fixed left-1/2 top-[calc(0.75rem+env(safe-area-inset-top))] z-50 max-w-[calc(100vw-1rem)] -translate-x-1/2 rounded-full border border-border/70 bg-popover px-4 py-2 text-sm font-medium text-popover-foreground shadow-lg"
        >
          {restartToast}
        </div>
      ) : null}
      <PairingCodePopup
        requests={visiblePairingRequests}
        total={visiblePairingRequests.length}
        busyCode={pairingBusyCode}
        error={pairingError}
        onApprove={onApprovePairing}
        onDismiss={onDismissPairing}
      />
    </>
  );
}
