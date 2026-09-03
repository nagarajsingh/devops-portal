interface Props {
  repositoryName: string;
  referenceRepository: string;
  referenceBranch: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export default function ExistingRepositoryConfirmation({
  repositoryName,
  referenceRepository,
  referenceBranch,
  busy = false,
  onCancel,
  onConfirm,
}: Props) {
  return (
    <div className="existing-repo-confirm-backdrop" role="presentation">
      <section className="existing-repo-confirm-card" role="dialog" aria-modal="true" aria-labelledby="existing-repo-confirm-title">
        <div className="existing-repo-confirm-icon">!</div>
        <span className="eyebrow">EXISTING REPOSITORY</span>
        <h3 id="existing-repo-confirm-title">Create the DevOps pipeline branch?</h3>
        <p>The repository already contains code. Only a new <strong>devops/pipeline</strong> branch will be created from the selected reference template.</p>
        <div className="existing-repo-confirm-details">
          <span>Target repository</span><strong>{repositoryName}</strong>
          <span>Template source</span><strong>{referenceRepository}:{referenceBranch || "develop"}</strong>
          <span>New branch</span><strong>devops/pipeline</strong>
        </div>
        <div className="existing-repo-confirm-note">Existing branches and application code will not be modified. Selecting Cancel leaves the repository unchanged.</div>
        <div className="existing-repo-confirm-actions">
          <button type="button" className="secondary-button" disabled={busy} onClick={onCancel}>Cancel</button>
          <button type="button" className="primary-button" disabled={busy} onClick={onConfirm}>{busy ? "Creating branch..." : "Yes, create branch"}</button>
        </div>
      </section>
    </div>
  );
}
