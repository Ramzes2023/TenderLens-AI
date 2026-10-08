"""Browser organization-management and workspace switching UI."""

ORGANIZATION_SCRIPT = r"""
state.organizations=[];
state.organizationId=null;
state.organizationRole=null;

function selectedOrganization(){
  return state.organizations.find(
    item=>item.id===state.organizationId
  )||null;
}

function organizationBase(){
  if(!Number.isInteger(state.organizationId)){
    throw new Error('Select an organization first.');
  }

  return `/api/v1/organizations/${state.organizationId}`;
}

function usingSharedOrganization(){
  const organization=selectedOrganization();

  return Boolean(
    organization
    && !organization.personal
  );
}

function canWriteWorkspace(){
  if(!usingSharedOrganization()){
    return true;
  }

  return [
    'owner',
    'admin',
    'member'
  ].includes(
    state.organizationRole
  );
}

function canManageOrganization(){
  return [
    'owner',
    'admin'
  ].includes(
    state.organizationRole
  );
}

function updateWorkspaceControls(){
  const organization=selectedOrganization();

  const add=document.getElementById(
    'addCompanyButton'
  );

  const scan=document.getElementById(
    'scanButton'
  );

  const scope=document.getElementById(
    'companyScopeLabel'
  );

  if(scope){
    scope.textContent=usingSharedOrganization()
      ? `Shared organization: ${organization?.name||''}`
      : 'Personal account workspace';
  }

  if(add){
    add.disabled=!canWriteWorkspace();

    add.title=canWriteWorkspace()
      ?''
      :'Viewer role is read-only.';
  }

  if(scan){
    scan.disabled=
      !state.hasActiveCompany
      || !canWriteWorkspace();

    scan.title=!canWriteWorkspace()
      ?'Viewer role is read-only.'
      :(
        state.hasActiveCompany
          ?''
          :'Create a company profile first.'
      );
  }
}

async function loadWorkspaceData(){
  await Promise.all([
    loadCompanies(),
    loadMonitoring(),
    loadTenders()
  ]);

  updateWorkspaceControls();
}

async function loadOrganizations(){
  const [items,defaultOrganization]=await Promise.all([
    api('/api/v1/organizations'),
    api('/api/v1/organizations/default')
  ]);

  state.organizations=items;

  const select=document.getElementById(
    'organizationSelect'
  );

  const previous=state.organizationId;

  select.innerHTML=items.map(item=>{
    const duplicate=items.some(other=>other.id!==item.id && other.name===item.name);
    const name=duplicate?`${item.name} · #${item.id}`:item.name;
    const label=item.personal
      ?`${name} · PERSONAL`
      :name;

    return `<option value="${item.id}">${esc(label)}</option>`;
  }).join('');

  if(
    Number.isInteger(previous)
    && items.some(
      item=>item.id===previous
    )
  ){
    state.organizationId=previous;
  }else{
    state.organizationId=
      defaultOrganization.id;
  }

  select.value=String(
    state.organizationId
  );

  document.getElementById(
    'organizationCount'
  ).textContent=String(
    items.length
  );

  await loadOrganizationManagement();
}

async function selectOrganization(){
  const value=Number(
    document.getElementById(
      'organizationSelect'
    ).value
  );

  if(
    !Number.isInteger(value)
    || value<=0
  ){
    return;
  }

  state.organizationId=value;

  clearInviteLink();

  await loadOrganizationManagement();

  await loadWorkspaceData();
}

async function createOrganization(){
  const input=document.getElementById(
    'newOrganizationName'
  );

  const button=document.getElementById(
    'createOrganizationButton'
  );

  const message=document.getElementById(
    'organizationMessage'
  );

  message.innerHTML='';

  const name=input.value.trim();

  if(!name){
    message.innerHTML=
      '<div class="error">Enter an organization name.</div>';

    return;
  }

  try{
    button.disabled=true;
    button.textContent='Creating...';

    const created=await api(
      '/api/v1/organizations',
      {
        method:'POST',
        body:JSON.stringify({
          name
        })
      }
    );

    input.value='';

    await loadOrganizations();

    state.organizationId=created.id;

    document.getElementById(
      'organizationSelect'
    ).value=String(created.id);

    await loadOrganizationManagement();

    await loadWorkspaceData();

    message.innerHTML=
      '<div class="success">Organization created and selected.</div>';

  }catch(e){
    message.innerHTML=
      `<div class="error">${esc(e.message||e)}</div>`;

  }finally{
    button.disabled=false;
    button.textContent=
      'Create organization';
  }
}

function memberRoleOptions(member){
  if(
    state.organizationRole==='admin'
    && member.role==='owner'
  ){
    return `<option value="owner" selected>owner</option>`;
  }

  const roles=state.organizationRole==='owner'
    ?[
        'owner',
        'admin',
        'member',
        'viewer'
      ]
    :[
        'admin',
        'member',
        'viewer'
      ];

  return roles.map(role=>
    `<option value="${role}" ${role===member.role?'selected':''}>${role}</option>`
  ).join('');
}

function renderManagerMember(member){
  const protectedOwner=
    state.organizationRole==='admin'
    && member.role==='owner';

  const controls=protectedOwner
    ?'<span class="chip">Owner</span>'
    :`
      <select
        style="width:auto"
        onchange="updateOrganizationMemberRole(${member.account_id},this.value)">
        ${memberRoleOptions(member)}
      </select>
      <button
        onclick="removeOrganizationMember(${member.account_id})">
        Remove
      </button>
    `;

  return `
    <div class="row">
      <div class="head">
        <div>
          <div class="title">
            Account #${member.account_id}
            ${member.account_id===state.accountId?'<span class="active"> YOU</span>':''}
          </div>
          <div class="sub">
            Role: ${esc(member.role)}
          </div>
        </div>
        <div class="toolbar">
          ${controls}
        </div>
      </div>
    </div>
  `;
}

async function loadOrganizationManagement(){
  const organization=selectedOrganization();

  const membersRoot=document.getElementById(
    'organizationMembers'
  );

  const invitesRoot=document.getElementById(
    'organizationInvitations'
  );

  const managerRoot=document.getElementById(
    'organizationManagerControls'
  );

  const title=document.getElementById(
    'selectedOrganizationName'
  );

  state.organizationRole=null;

  if(!organization){
    title.textContent=
      'No organization selected';

    membersRoot.innerHTML=
      '<div class="empty">No organization selected.</div>';

    invitesRoot.innerHTML='';

    managerRoot.classList.add(
      'hidden'
    );

    updateWorkspaceControls();

    return;
  }

  title.textContent=organization.name;

  try{
    const own=await api(
      `${organizationBase()}/membership/me`
    );

    state.organizationRole=own.role;

  }catch(e){
    membersRoot.innerHTML=
      `<div class="error">${esc(e.message||e)}</div>`;

    invitesRoot.innerHTML='';

    managerRoot.classList.add(
      'hidden'
    );

    updateWorkspaceControls();

    return;
  }

  if(organization.personal){
    membersRoot.innerHTML=
      `<div class="empty">
        Personal account workspace; role:
        <b>${esc(state.organizationRole)}</b>.
        Your companies and analyzed documents are private to your account.
      </div>`;

    invitesRoot.innerHTML=
      '<div class="empty">Create a shared organization to collaborate with teammates.</div>';

    managerRoot.classList.add(
      'hidden'
    );

    updateWorkspaceControls();

    return;
  }

  if(!canManageOrganization()){
    membersRoot.innerHTML=
      `<div class="empty">
        Your role in this organization:
        <b>${esc(state.organizationRole)}</b>.
        Member management is available to owners and admins.
      </div>`;

    invitesRoot.innerHTML=
      '<div class="empty">Pending invitations are visible to organization owners and admins.</div>';

    managerRoot.classList.add(
      'hidden'
    );

    updateWorkspaceControls();

    return;
  }

  try{
    const members=await api(
      `${organizationBase()}/members`
    );

    membersRoot.innerHTML=members.length
      ?members.map(
          renderManagerMember
        ).join('')
      :'<div class="empty">No members found.</div>';

    managerRoot.classList.remove(
      'hidden'
    );

    await loadOrganizationInvitations();

  }catch(e){
    membersRoot.innerHTML=
      `<div class="error">${esc(e.message||e)}</div>`;

    invitesRoot.innerHTML='';

    managerRoot.classList.add(
      'hidden'
    );
  }

  updateWorkspaceControls();
}

async function updateOrganizationMemberRole(
  accountId,
  role
){
  try{
    await api(
      `${organizationBase()}/members/${accountId}`,
      {
        method:'PATCH',
        body:JSON.stringify({
          role
        })
      }
    );

    await loadOrganizationManagement();

  }catch(e){
    document.getElementById(
      'organizationMessage'
    ).innerHTML=
      `<div class="error">${esc(e.message||e)}</div>`;

    await loadOrganizationManagement();
  }
}

async function removeOrganizationMember(
  accountId
){
  if(
    !confirm(
      'Remove this member from the organization?'
    )
  ){
    return;
  }

  try{
    await api(
      `${organizationBase()}/members/${accountId}`,
      {
        method:'DELETE'
      }
    );

    await loadOrganizationManagement();

    await loadWorkspaceData();

  }catch(e){
    document.getElementById(
      'organizationMessage'
    ).innerHTML=
      `<div class="error">${esc(e.message||e)}</div>`;
  }
}

async function loadOrganizationInvitations(){
  const root=document.getElementById(
    'organizationInvitations'
  );

  try{
    const items=await api(
      `${organizationBase()}/invitations`
    );

    root.innerHTML=items.length
      ?items.map(item=>
          `<div class="row">
            <div class="head">
              <div>
                <div class="title">
                  ${esc(item.email)}
                </div>
                <div class="sub">
                  ${esc(item.role)}
                 ; expires ${esc(item.expires_at)}
                </div>
              </div>
              <button onclick="revokeOrganizationInvitation(${item.id})">
                Revoke
              </button>
            </div>
          </div>`
        ).join('')
      :'<div class="empty">No pending invitations.</div>';

  }catch(e){
    root.innerHTML=
      `<div class="error">${esc(e.message||e)}</div>`;
  }
}

async function createOrganizationInvitation(){
  if(
    !usingSharedOrganization()
  ){
    return;
  }

  const email=document.getElementById(
    'inviteEmail'
  ).value.trim();

  const role=document.getElementById(
    'inviteRole'
  ).value;

  const button=document.getElementById(
    'inviteButton'
  );

  const message=document.getElementById(
    'inviteMessage'
  );

  message.innerHTML='';

  if(!email){
    message.innerHTML=
      '<div class="error">Enter an email address.</div>';

    return;
  }

  try{
    button.disabled=true;
    button.textContent='Creating...';

    const created=await api(
      `${organizationBase()}/invitations`,
      {
        method:'POST',
        body:JSON.stringify({
          email,
          role
        })
      }
    );

    document.getElementById(
      'inviteEmail'
    ).value='';

    const link=
      `${location.origin}/invite/${encodeURIComponent(created.token)}`;

    document.getElementById(
      'inviteLink'
    ).value=link;

    document.getElementById(
      'inviteLinkRoot'
    ).classList.remove(
      'hidden'
    );

    message.innerHTML=
      '<div class="success">Invitation created. Copy and share this link with your teammate now; it will not be shown again.</div>';

    await loadOrganizationInvitations();

  }catch(e){
    message.innerHTML=
      `<div class="error">${esc(e.message||e)}</div>`;

  }finally{
    button.disabled=false;
    button.textContent=
      'Create invitation';
  }
}

function clearInviteLink(){
  const root=document.getElementById(
    'inviteLinkRoot'
  );

  if(root){
    root.classList.add(
      'hidden'
    );
  }

  const input=document.getElementById(
    'inviteLink'
  );

  if(input){
    input.value='';
  }

  const message=document.getElementById(
    'inviteMessage'
  );

  if(message){
    message.innerHTML='';
  }
}

async function copyInviteLink(){
  const input=document.getElementById(
    'inviteLink'
  );

  if(!input.value){
    return;
  }

  try{
    await navigator.clipboard.writeText(
      input.value
    );

  }catch(_){
    input.focus();
    input.select();

    let copied=false;
    try{copied=Boolean(document.execCommand?.('copy'));}catch(_){}
    if(!copied){
      document.getElementById('inviteMessage').innerHTML=
        '<div class="error">Automatic copying is unavailable. Select and copy the invitation link manually.</div>';
      return;
    }
  }

  document.getElementById(
    'inviteMessage'
  ).innerHTML=
    '<div class="success">Invitation link copied.</div>';
}

async function revokeOrganizationInvitation(id){
  if(
    !confirm(
      'Revoke this invitation?'
    )
  ){
    return;
  }

  try{
    await api(
      `${organizationBase()}/invitations/${id}`,
      {
        method:'DELETE'
      }
    );

    await loadOrganizationInvitations();

  }catch(e){
    document.getElementById(
      'inviteMessage'
    ).innerHTML=
      `<div class="error">${esc(e.message||e)}</div>`;
  }
}
"""

__all__ = [
    "ORGANIZATION_SCRIPT",
]
