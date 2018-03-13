import argparse
import kubernetes
import re
import yaml

parser = argparse.ArgumentParser(description='Updates RBAC cluster role bindings and role bindings.')
parser.add_argument('--config', help='YAML configuration file to load', required=True)
args = parser.parse_args()

print("---")
print("Connecting to Kubernetes API")

k8s_config_loaded = False

try:
  print("Attempting to load incluster config")
  kubernetes.config.load_incluster_config()
  print("Successfully loaded incluster config")
  k8s_config_loaded = True
except:
  print("Loading incluster config failed")

if k8s_config_loaded != True:
  try:
    print("Attempting to load kube config")
    kubernetes.config.load_kube_config()
    k8s_config_loaded = True
    print("Successfully loaded kube config")
  except:
    print("Loading kube config failed, exiting")
    exit(1)

rbac_client = kubernetes.client.RbacAuthorizationV1Api()

requested_role_bindings = []
requested_cluster_role_bindings = []

print("---")
print("Finding existing Cluster Role Bindings")

rb_response = rbac_client.list_role_binding_for_all_namespaces(label_selector="rbac-manager=reactiveops")
existing_managed_role_bindings = rb_response.items

print("---")
print("Finding existing Role Bindings")

crb_response = rbac_client.list_cluster_role_binding(label_selector="rbac-manager=reactiveops")
existing_managed_cluster_role_bindings = crb_response.items

print("---")
print("Parsing provided RBAC configuration file")

rbac_users = yaml.load(open(args.config))

labels={"rbac-manager": "reactiveops"}

for rbac_user in rbac_users:
  subject = kubernetes.client.V1Subject(kind="User", name=rbac_user['user'])
  if 'clusterRoleBindings' in rbac_user:
    for cluster_role_binding in rbac_user['clusterRoleBindings']:
      role_ref = kubernetes.client.V1RoleRef(
        api_group="rbac.authorization.k8s.io",
        kind="ClusterRole",
        name=cluster_role_binding['clusterRole']
      )
      role_binding_name = "{}-{}".format(re.sub('[^A-Za-z0-9]+', '-', rbac_user['user']), cluster_role_binding['clusterRole'])
      metadata = kubernetes.client.V1ObjectMeta(name=role_binding_name, labels=labels)
      cluster_role_binding = kubernetes.client.V1ClusterRoleBinding(
        metadata=metadata,
        role_ref=role_ref,
        subjects=[subject]
      )

      requested_cluster_role_bindings.append(cluster_role_binding)


  if 'roleBindings' in rbac_user:
    for role_binding in rbac_user['roleBindings']:
      if 'clusterRole' in role_binding:
        role=role_binding['clusterRole']
        role_ref = kubernetes.client.V1RoleRef(
          api_group="rbac.authorization.k8s.io",
          kind="ClusterRole",
          name=role
        )
      elif 'role' in role_binding:
        role=role_binding['role']
        role_ref = kubernetes.client.V1RoleRef(
          api_group="rbac.authorization.k8s.io",
          kind="Role",
          name=role
        )
      else:
        print("Invalid role binding, requires 'role' or 'clusterRole' attribute")
        break

      if 'namespace' in role_binding:
        namespace=role_binding['namespace']
      else:
        print("Invalid role binding, requires 'namespace' attribute")
        break

      role_binding_name = "{}-{}-{}".format(re.sub('[^A-Za-z0-9]+', '-', rbac_user['user']), namespace, role)
      metadata = kubernetes.client.V1ObjectMeta(
        name=role_binding_name,
        namespace=namespace,
        labels=labels
      )
      role_binding = kubernetes.client.V1RoleBinding(
        metadata=metadata,
        role_ref=role_ref,
        subjects=[subject]
      )

      requested_role_bindings.append(role_binding)


cluster_role_bindings_to_create = requested_cluster_role_bindings[:]
cluster_role_bindings_to_delete = existing_managed_cluster_role_bindings[:]

print("---")

print("Comparing requested Cluster Role Bindings with existing ones")
for rcrb in requested_cluster_role_bindings:
  for ecrb in existing_managed_cluster_role_bindings:
    if rcrb.metadata.name == ecrb.metadata.name:
      print("Existing Cluster Role Binding found for {}".format(rcrb.metadata.name))
      cluster_role_bindings_to_create.remove(rcrb)
      cluster_role_bindings_to_delete.remove(ecrb)
      break


role_bindings_to_create = requested_role_bindings[:]
role_bindings_to_delete = existing_managed_role_bindings[:]

print("---")

print("Comparing requested Role Bindings with existing ones")
for rrb in requested_role_bindings:
  for erb in existing_managed_role_bindings:
    if rrb.metadata.name == erb.metadata.name:
      print("Existing Role Binding found for {}".format(rrb.metadata.name))
      role_bindings_to_create.remove(rrb)
      role_bindings_to_delete.remove(erb)
      break

print("---")

if len(cluster_role_bindings_to_create) < 1:
  print("No Cluster Role Bindings need to be created")
else:
  print("Creating Cluster Role Bindings")
  for crb in cluster_role_bindings_to_create:
    print("Creating Cluster Role Binding: {}".format(crb.metadata.name))
    rbac_client.create_cluster_role_binding(
      body=crb,
      pretty=True
    )

print("---")

if len(cluster_role_bindings_to_delete) < 1:
  print("No Cluster Role Bindings need to be deleted")
else:
  print("Deleting Cluster Role Bindings")
  for crb in cluster_role_bindings_to_delete:
    print("Deleting Cluster Role Binding: {}".format(crb.metadata.name))
    rbac_client.delete_cluster_role_binding(
      name=crb.metadata.name,
      body=kubernetes.client.V1DeleteOptions(),
      pretty=True
    )

print("---")

if len(role_bindings_to_create) < 1:
  print("No Role Bindings need to be created")
else:
  print("Creating Role Bindings")
  for rb in role_bindings_to_create:
    print("Creating Role Binding: {} in {}".format(rb.metadata.name, rb.metadata.namespace))
    rbac_client.create_namespaced_role_binding(
      namespace=rb.metadata.namespace,
      body=rb,
      pretty=True
    )

print("---")

if len(role_bindings_to_delete) < 1:
  print("No Role Bindings need to be deleted")
else:
  print("Deleting Role Bindings")
  for rb in role_bindings_to_delete:
    print("Deleting Role Binding: {} in {}".format(rb.metadata.name, rb.metadata.namespace))
    rbac_client.delete_namespaced_role_binding(
      namespace=rb.metadata.namespace,
      name=rb.metadata.name,
      body=kubernetes.client.V1DeleteOptions(),
      pretty=True
    )

print("---")
