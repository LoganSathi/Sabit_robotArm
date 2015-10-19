import numpy as np
from . import forward_kinematics as fk
from . import inverse_kinematic as ik
from . import plot_utils as pl
from .tools import transformations as tr


class Model(object):

    def __init__(self, links, rot=None, trans=None, representation="euler", model_type="custom", pypot_object=None, computation_method="default", simplify=False):
        # Configuration 2D
        self.links = links
        self.nb_joints = len(links)
        self.init_params(links)
        self.model_type = model_type
        self.computation_method = computation_method
        # set the transformations from world to base
        self.set_base_transformations(rot, trans)
        # initialize starting configuration
        self.current_joints = np.zeros(len(links))
        self.representation = representation
        self.pypot_object = pypot_object
        if self.computation_method == "symbolic":
            # Compute the transformation matrix only if the computation_method is "symbolic"
            self.simplify = simplify
            self.symbolic_transformation_matrix = fk.compute_symbolic_rotation_matrix(self.parameters, representation=self.representation, model_type=self.model_type, simplify=self.simplify)
        elif self.computation_method == "hybrid":
            self.simplify = simplify
            self.hybrid_transformation_matrixes = fk.compute_rotation_matrixes(self.parameters, representation=self.representation, model_type=self.model_type, simplify=self.simplify)
        self.current_pose = self.forward_kinematic(self.current_joints)
        self.target = self.current_pose

    def sym_mat(self, *args, **kwargs):
        return self.symbolic_transformation_matrix(*args, **kwargs)

    def set_base_transformations(self, rot=None, trans=None):
        if rot is None:
            rot = np.eye(3)
        if trans is None:
            trans = [0, 0, 0]
        self.world_to_base = tr.transformation(rot, trans)
        self.base_to_world = tr.inverse_transform(self.world_to_base)

    def init_params_2d(self, links):
        vectors = []
        for l in links:
            vectors.append(([0, 0, 1], [l, 0, 0]))
        self.parameters = fk.euler_from_URDF_parameters(vectors)

    def init_params(self, links):
        self.parameters = links
        self.arm_length = self.get_robot_length()
        # print(self.arm_length)

    def set_max_velocity(self, v):
        self.max_velocity = v

    def forward_kinematic(self, q=None):
        """Renvoie la position du end effector en fonction de la configuration des joints"""
        if q is None:
            q = self.current_joints
        # calculate the forward kinematic
        if self.computation_method == "default":
            X = fk.get_nodes(self.parameters, q, representation=self.representation, model_type=self.model_type)["positions"][-1]

        elif self.computation_method == "symbolic":
            # On applique la matrice transformation au vecteur [0, 0, 0]
            X = fk.get_node_symbolic(self.sym_mat, q)
        elif self.computation_method == "hybrid":
            X = fk.get_node_hybrid(self.hybrid_transformation_matrixes, q)
        # return the result in the world frame
        W_X = tr.transform_point(X, self.world_to_base)
        return W_X

    def inverse_kinematic_raw(self, W_X, seed=None):
        if seed is None:
            seed = self.current_joints
        # calculate the coordinate of the target in the robot frame
        X = tr.transform_point(W_X, self.base_to_world)
        # return the inverse kinematic
        return ik.inverse_kinematic(self.parameters, seed, X, model_type=self.model_type, representation=self.representation)

    def inverse_kinematic_raw_symbolic(self, absolute_target, seed=None):
        if seed is None:
            seed = self.current_joints
        # calculate the coordinate of the target in the robot frame
        target = tr.transform_point(absolute_target, self.base_to_world)
        return ik.inverse_kinematic_transformation_matrix(self.sym_mat, seed, target)

    def inverse_kinematic_raw_hybrid(self, absolute_target, seed=None):
        if seed is None:
            seed = self.current_joints
        # calculate the coordinate of the target in the robot frame
        target = tr.transform_point(absolute_target, self.base_to_world)
        return ik.inverse_kinematic_hybrid(self.hybrid_transformation_matrixes, seed, target)

    def inverse_kinematic(self, absolute_target):
        """Computes the IK for given target"""
        # Choose computation method
        if self.computation_method == "default":
            return self.inverse_kinematic_raw(absolute_target, self.current_joints)
        elif self.computation_method == "symbolic":
            return self.inverse_kinematic_raw_symbolic(absolute_target, self.current_joints)
        elif self.computation_method == "hybrid":
            return self.inverse_kinematic_raw_hybrid(absolute_target, self.current_joints)

    def set_current_joints(self, q):
        self.current_joints = q

    def goto_target(self):
        """Déplace le robot vers la target donnée"""
        self.goal_joints = self.inverse_kinematic(self.target)

        if self.pypot_object is not None:
            # Si un robot pypot est attaché au modèle, on demande au robot d'aller vers les angles voulus
            self.pypot_sync_goal_joints()

            # On actualise la position des joints
            self.pypot_sync_current_joints()

        else:
            # Sinon on place le modèle directement dans la position voulue
            self.current_joints = self.goal_joints

    def pypot_sync_goal_joints(self):
        """Synchronise les valeurs de goal_joints"""
        if self.pypot_object is not None:
            for i, m in enumerate(self.pypot_object.motors):
                m.goal_position = self.goal_joints[i] * 180 / (np.pi / 2)

    def pypot_sync_current_joints(self):
        """Synchronise les valeurs de current_joints"""

    def plot_model(self, q=None):
        """Affiche le modèle du robot"""
        if q is None:
            q = self.current_joints
        ax = pl.init_3d_figure()
        pl.plot_robot(self.parameters, q, ax, representation=self.representation, model_type=self.model_type)
        pl.plot_basis(self.parameters, ax, self.arm_length)

        # Plot the goal position
        if self.target is not None:
            pl.plot_target(self.target, ax)
        pl.show_figure()

    def get_robot_length(self):
        """Calcul la longueur du robot (tendu)"""
        translations_vectors = [x[0] for x in self.parameters]
        joints_lengths = [np.sqrt(sum([x**2 for x in vector]))
                          for vector in translations_vectors]
        return sum(joints_lengths)
