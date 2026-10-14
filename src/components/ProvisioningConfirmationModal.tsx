interface Props {
  open: boolean;
  type: "repository" | "pipeline";
  repositoryName: string;
  referenceRepository?: string;
  referenceBranch?: string;
  pipelineName?: string;
  remoteKubernetes?: boolean;
  busy?: boolean;
  onYes: () => void;
  onNo: () => void;
}

export default function ProvisioningConfirmationModal({ open, type, repositoryName, referenceRepository, referenceBranch, pipelineName, remoteKubernetes = false, busy = false, onYes, onNo }: Props) {
  if (!open) return null;
  const repositoryConfirmation = type === "repository";
  return <div className="existing-repo-confirm-backdrop" role="presentation">
    <div className="existing-repo-confirm-card" role="dialog" aria-modal="true" aria-labelledby="provisioning-confirm-title">
      <div className="existing-repo-confirm-icon">!</div>
      <span className="eyebrow">CONFIRM PROVISIONING ACTION</span>
      <h3 id="provisioning-confirm-title">{repositoryConfirmation ? "Repository already exists" : "Build pipeline already exists"}</h3>
      <p>{repositoryConfirmation
        ? "The repository already contains code. DevOps Portal will not modify any existing branch or application code."
        : remoteKubernetes
          ? "The build pipeline is already available. This target uses the remote Kubernetes provisioning pipeline, so Service and Ingress work can complete independently while release-pipeline reuse waits for confirmation."
          : "The build pipeline is already available. Confirm whether it should be reused so release-pipeline creation and direct Kubernetes provisioning can continue."}</p>
      <div className="existing-repo-confirm-details">
        <span>Application repository</span><strong>{repositoryName}</strong>
        {repositoryConfirmation ? <><span>Reference</span><strong>{referenceRepository || "—"}:{referenceBranch || "develop"}</strong><span>Action</span><strong>Create isolated pipeline branch and continue</strong></> : <><span>Existing build pipeline</span><strong>{pipelineName || repositoryName}</strong><span>Next action</span><strong>Create / clone the release pipeline using this build pipeline</strong></>}
      </div>
      <div className="existing-repo-confirm-note">{repositoryConfirmation
        ? "No existing branches or code will be overwritten. If develop exists, the onboarding branch is created from it and a PR is raised back to develop."
        : remoteKubernetes
          ? "Selecting No stops release-pipeline creation. Any remote Kubernetes Service or Ingress work that already completed is preserved, and the existing build pipeline is not modified."
          : "Selecting No keeps release-pipeline, Service and Ingress provisioning paused. The existing build pipeline is not modified."}</div>
      <div className="existing-repo-confirm-actions">
        <button className="secondary-button" disabled={busy} onClick={onNo}>No</button>
        <button className="primary-button" disabled={busy} onClick={onYes}>{busy ? "Processing..." : "Yes, continue"}</button>
      </div>
    </div>
  </div>;
}
