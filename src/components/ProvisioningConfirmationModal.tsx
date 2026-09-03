interface Props {
  open: boolean;
  type: "repository" | "pipeline";
  repositoryName: string;
  referenceRepository?: string;
  referenceBranch?: string;
  pipelineName?: string;
  busy?: boolean;
  onYes: () => void;
  onNo: () => void;
}

export default function ProvisioningConfirmationModal({ open, type, repositoryName, referenceRepository, referenceBranch, pipelineName, busy = false, onYes, onNo }: Props) {
  if (!open) return null;
  const repositoryConfirmation = type === "repository";
  return <div className="existing-repo-confirm-backdrop" role="presentation">
    <div className="existing-repo-confirm-card" role="dialog" aria-modal="true" aria-labelledby="provisioning-confirm-title">
      <div className="existing-repo-confirm-icon">!</div>
      <span className="eyebrow">CONFIRM PROVISIONING ACTION</span>
      <h3 id="provisioning-confirm-title">{repositoryConfirmation ? "Repository already exists" : "Build pipeline already exists"}</h3>
      <p>{repositoryConfirmation
        ? "The repository already contains code. DevOps Portal will not modify any existing branch or application code."
        : "The build pipeline is already available. Confirm whether the existing pipeline should be reused to create the release pipeline."}</p>
      <div className="existing-repo-confirm-details">
        <span>Application repository</span><strong>{repositoryName}</strong>
        {repositoryConfirmation ? <><span>Reference</span><strong>{referenceRepository || "—"}:{referenceBranch || "develop"}</strong><span>Action</span><strong>Create isolated pipeline branch and continue</strong></> : <><span>Existing build pipeline</span><strong>{pipelineName || repositoryName}</strong><span>Next action</span><strong>Create / clone the release pipeline using this build pipeline</strong></>}
      </div>
      <div className="existing-repo-confirm-note">{repositoryConfirmation
        ? "No existing branches or code will be overwritten. If develop exists, the onboarding branch is created from it and a PR is raised back to develop."
        : "Selecting No stops the workflow before release pipeline creation. The existing build pipeline is not modified."}</div>
      <div className="existing-repo-confirm-actions">
        <button className="secondary-button" disabled={busy} onClick={onNo}>No</button>
        <button className="primary-button" disabled={busy} onClick={onYes}>{busy ? "Processing..." : "Yes, continue"}</button>
      </div>
    </div>
  </div>;
}
