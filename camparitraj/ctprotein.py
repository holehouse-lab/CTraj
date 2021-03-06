"""
CTProtein is the main protein trajectory class in CAMPARITRAJ

"""

##
##                                       _ _              _ 
##   ___ __ _ _ __ ___  _ __   __ _ _ __(_) |_ _ __ __ _ (_)
##  / __/ _` | '_ ` _ \| '_ \ / _` | '__| | __| '__/ _` || |
## | (_| (_| | | | | | | |_) | (_| | |  | | |_| | | (_| || |
##  \___\__,_|_| |_| |_| .__/ \__,_|_|  |_|\__|_|  \__,_|/ |
##                     |_|                             |__/ 
##
##
## Alex Holehouse (Pappu Lab and Holehouse Lab)
## Simulation analysis package
## Copyright 2014 - 2021
##

import mdtraj as md
import numpy as np
from numpy import linalg as LA
from itertools import combinations
from scipy import stats
import scipy.optimize as SPO
from numpy.random import choice

from .configs import DEBUGGING
from .ctdata import THREE_TO_ONE, DEFAULT_SIDECHAIN_VECTOR_ATOMS, ALL_VALID_RESIDUE_NAMES
from .ctexceptions import CTException
from . import ctmutualinformation, ctio, cttools, ctpolymer, ctutils

from . _internal_data import BBSEG2

import scipy.cluster.hierarchy


## Order of standard args:
## 1. correctOffset
## 2. stride
## 3. weights
#  4. verbose
##
##


class CTProtein:
    """

    CTProtein objects are initialized with a trajectory subset that contains only the atoms 
    a specific, single protein. This means that a CTProtein object allows operations to 
    performed on a single protein. A single trajectory may have multiple proteins in it.
    indexing with a protein object assumes that the protein is indexed from 0 to `n`,
    `n` is the number of residues. 
    
    **This is an important idea to emphasize - it means that you (the user) will need to determine 
    the correct residue index for a region of interest being examined. The region will NOT 
    (necessarily) correspond to the residue index in the PDB file used.**

    To make this easier the function `CTProtein.print_residues()` will print the mapping of residue 
    index to residue name and residue number. 

    To re-iterate:

    **Residue number is the number of the residue in the PDB file.**

    Residue index is the index value associated with a residue in a specific protein
    and will always begin from 0 - note this will include the peptide caps (ACE/NME)
    if present.

    """

    ## >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    ##
    ## A note for the code:
    ## The residue offset operation is performed by the __get_offset_residue fuction.
    ## For ANY function where a specific residue is supplied there must also be the
    ## option to perform this offset or not (i.e. each public facicing function
    ## should be able to stand alone and not rely on an offset being performed
    ## by another function) BUT the option to perform the offseting provided so it
    ## in functions that call other functions which can perform the offset it will
    ## only need to be performed once.
    ##
    ## >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    

    # ........................................................................
    #
    def __init__(self, traj, residue_offset):
        """
        Initialize a CTProtein object instance using trajectory information, and information
        about offsets.

        Parameters
        ----------
        traj: `cttrajectory.CTTrajectory`
            An instance of a system's trajectory populated via `cttrajectory.CTTrajectory`.

        residue_offset: int
            Similar to `atom_offset`, this is the residue index which will serve as the marker
            for residue index 0.

            The residue offset operation is performed by the `__get_offset_residue` fuction.
            For ANY function where a specific residue is supplied there must also be the
            option to perform this offset or not (i.e. each public facing function
            should be able to stand alone and not rely on an offset being performed
            by another function) BUT the option to perform the offseting provided so it
            in functions that call other functions which can perform the offset it will
            only need to be performed once.

        """
        
        # set the trajectory object for easy access
        self.traj     = traj
        self.topology = traj.topology

        # WARNING - at the moment it seems that while the trajectory
        # is a subset of full trajectory, the topology retains 
        # its full content of RESIDUES (though not atoms)
        # this is somewhat annoying


        # same for residue o
        self.residue_offset = residue_offset

        if DEBUGGING:
            ctio.debug_message("Creating protein")            
            ctio.debug_message("Residue offset : " + str(residue_offset))
            r_string = ''
            for r in self.topology.chain(0).residues:
                r_string = r_string + (str)
            ctio.debug_message("Residue string from residues in self.topology.chain(0).residues: %s" %(r_string))

            # delete the vaiable to avoid any possible introduction of this var into the namespace
            del r_string
            
                
        
        # initialze various protein-centric data
        self.__num_residues       = sum( 1 for _ in self.topology.residues)

        # initialize some empty values that are populated on demand by functions that drive local
        # memoization.
        self.__amino_acids_3LTR   = None
        self.__amino_acids_1LTR   = None
        self.__residue_index_list = None
        self.__CA_residue_atom    = {}
        self.__residue_atom_table = {}
        self.__residue_COM        = {}

        (self.__resid_with_CA, self.__idx_with_CA) = self.__get_resid_with_CA()

        # define if caps are present or not - specifically, if the resid 0 is in the CA-containing
        if 0 in self.resid_with_CA:
            self.__ncap = False
        else:
            self.__ncap = True

        if (self.n_residues - 1) in self.idx_with_CA:
            self.__ccap = False
        else:
            self.__ccap = True


    # <><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><>
    #
    # Properties


    @property
    def resid_with_CA(self):
        """
        Return a list of resids that have CA atoms. Note these residues have already have their
        offset correction applied, and so are valid to be used for selection via the underlying
        mdtraj topology object (self.topology).

        The values associated with this property are built using the internal function `__get_resid_with_CA()`

        Returns
        --------
        list of integers

                
        See Also
        ------------
        idx_with_CA

        """
        return self.__resid_with_CA


    @property
    def idx_with_CA(self):
        """
        Return a list of zero-indexed IDs that have CA atoms. Note these indices start at zero regardless of what
        the internal .topology resid numbering is. Recall that for for mdtraj 1.9.5 or greater this should be the
        same as the values returned by `resid_with_CA`.

        The values associated with this property are built using the internal function `__get_resid_with_CA()`

        Returns
        --------
        list of integers

                
        See Also
        ------------
        resid_with_CA

        """

        return self.__idx_with_CA

    @property
    def ncap(self):
        """
        Flag that returns if an N-terminal capping residue is present (or not).

        Returns
        ----------
        bool
            True if N-teminal cap is present, False if not

        """
        return self.__ncap

    @property
    def ccap(self):
        """
        Flag that returns if a C-terminal capping residue is present (or not).

        Returns
        ----------
        bool
            True if C-teminal cap is present, False if not

        """

        return self.__ccap

    @property
    def n_frames(self):
        """
        Returns the number of frames in the trajectory

        Returns
        ----------
        int
            Returns the number of frames in the simulation trajectory

        """

        return self.traj.n_frames

    @property
    def n_residues(self):
        """
        Returns the number of residues in the protein (including caps)

        Returns
        ----------
        int
            Returns the number of frames in the protein

        """

        return self.__num_residues

    @property
    def residue_index_list(self):
        """
        Returns the list of residue index values for this protein. 
        i.e. this is the correctly offset residue list and will include NME/ACE
        caps if present.

        For backend implementation details, this returns the res.index values from
        all res in topology.residues (mdtraj.mdtrajectory)
        """

        if self.__residue_index_list == None:
            reslist = []
            for res in self.topology.residues:
                reslist.append(res.index)
                
            self.__residue_index_list = reslist
        return self.__residue_index_list



    def  __repr__(self):
        return "CTProtein (%s): %i res and %i frames" % (hex(id(self)), self.n_residues, self.n_frames)

    def __len__(self):
        return (self.n_residues, self.n_frames)

        
    # ........................................................................
    #
    def __check_weights(self, weights, stride=None):
        """
        Function that checks a passed weights-array is usable and matches the number of frames
        (avoids a lot of heartache when something breaks deep inside the code).

        NOTE: This also typecasts weights to a `numpy.array` which allows them to be indexed directly
        using a list of values.

        Parameters
        ----------
        weights : array_like
            An `numpy.array` object that corresponds to the number of frames within an input trajectory.
        stride : {None}, optional
            The stepsize used when iterating across the frames. A value of `None` will set the step
            size to 0.

        Returns
        -------
        numpy.array
            An `np.array` object containing trajectory frames selected per `stride` number of frames.
        """

        if weights is not False:
            if len(weights) != self.n_frames:
                raise CTException('Passed frame weights array is %i in length, while there are actually %i frames - these must match' % (len(weights), self.n_frames))

                
            if stride > 1:
                ctio.warning_message("WARNING: Using stride with weights is ALMOST certainly not a good idea unless the weights are\ncalculated for every stride-th residue", with_frills=True)
                return np.array(weights[list(range(0,self.n_frames,stride))])
            else:
                return np.array(weights)

        return False


    # ........................................................................
    #
    def __get_first_and_last(self, R1, R2, withCA=False):
        """
        Function which returns first and last residue for a range, correcting for the residue
        offset problem. The returned tup

        Parameters
        ----------
        R1 : int or False/None {False}
            First residue in range - can be an integer (assumes first residue in chain indexed at 0). 
            If `False` assume we start at 0.
        
        R2 : int or False/None {False}
            Last residue in range - can be an integer (assumes first residue in chain indexed at 0).
            If `False` assumes we're using the whole chain.

        withCA : bool {False}
            Flag which, if `True` and R1 or R2 are `False`, selects R1/R2 values that contain a CA, which basically
            means caps are dealt with here if present.

        Returns
        -------
        tuple:
            Returns a tuple with three positions:
        
            - [0] = R1 with relevant offsets applid (`int`).
            - [1] = R2 with relevant offsets applid (`int`).
            - [2] = String that can be passed directly to topology select to extract the atoms associated with these positions.

        """

        # first define as if we're starting from first and last residue with/without caps
        if R1 == False or R1 == None:
            if withCA:
                if self.ncap:
                    R1 = 1
                else:
                    R1 = 0
            else:
                R1 = 0

        if R2 == False or R2 == None:
            if withCA:
                if self.ccap:
                    R2 = self.n_residues - 2
                else:
                    R2 = self.n_residues - 1
            else:
                R2 = self.n_residues - 1

        # then apply the systematic offset
        R1 = R1 + self.residue_offset
        R2 = R2 + self.residue_offset

        # finally flip around if R1 is larger than R2
        if R1 > R2:
            tmp = R2
            R2 = R1
            R1 = tmp

        return (R1, R2, "resid %i to %i" %(R1,R2))
        

    # ........................................................................
    #
    def get_offset_residue(self, R1):
        """
        Returns the true residue index (TRI) for this protein by taking into
        account the residue offset. Checks the residue first to ensure a valid
        residue has been passed.

        NOTE: As of MDTraj 1.9.5 this is ACTUALLY overkill as when new trajectories
        are created the resid numbering resets to starting at 0 (as opposed to 
        retaining the old trajectory numbering). However, for 1.9.4 or lower this
        did not happen, such that usin the get_offset_residue() function provides
        long-lasting backwards compatibility.
        

        Parameters
        -----------
        R1: int
            The zero-indexed input residue offset (`int`). This value is
            examined by `__check_single_residue()`.

        Returns
        --------
        TRI: int
            The updated index which reflects the input offset to determine 
            the **true** starting residue index.

        See Also
        --------
        __check_single_residue

        """

        self.__check_single_residue(R1)

        return R1 + self.residue_offset

    # ........................................................................
    #
    def __check_stride(self, stride):
        """
        Checks that a passed stride value doesn't break everything. Returns `None`
        or raises a `CTException`.

        Parameters
        ----------

        stride: int
            The non-zero number of steps to perform while iterating across a
            trajectory.

        Raises
        ------
        CTException
            When the stride is larger than the number of available frames in the
            trajectory, or less than 1.

        """
        if stride > self.n_frames:
            raise CTException('stride (%i) is larger than the number of frames (%i)' %(stride, self.n_frames))

        if stride < 1:
            raise CTException('stride (%i) is less than 1' %(stride))
            
        

    # ........................................................................
    #
    def __check_single_residue(self, R1):
        """
        Internal function that checks that a single residue provided makes sense in the context of
        this protein. NOTE this checks BEFORE an offset is applied (i.e. we assume once a residue
        offset has been made that the resid's validity has been established).

        Returns `None` or raises a `CTException`.

        Parameters
        ----------
        R1: int
            The zero-indexed residue index (`int`) whose index is checked and validated.

        Raises
        ------
        CTException
            When the residue ID is greater than the chain length, or when the distances explored
            are greater than the chain size.

        """

        if R1 < 0:
            raise CTException("Trying to use a negative residue index [residue index = %i]"%R1)

        if R1  >= self.n_residues:
            raise CTException("Trying to use a residue ID greater than the chain length [residue index = %i, chain length = %i] " % (R1, self.n_residues))

        if (R1 - self.residue_offset) >= self.n_residues:
            raise CTException("Trying to explore distances greater than chain size [residue index = %i, chain length = %i] " % (R1, self.n_residues))


    # ........................................................................
    #
    def __check_contains_CA(self, R1, R1_org=None, has_correctOffset=True):
        """
        Function which checks if residue R1 (which is the residue AFTER an offset correction has 
        been applied) contains a C-alpha atom.

        Returns `None` or raises a `CTException`.

        Parameters
        ----------
        R1: int
            The zero-indexed residue index (`int`) whose index is checked and validated.

        R1_org: int or None {None}


        Raises
        ------
        CTException
            When the `CTProtein` has an uncorrected offset and residue `R1` lacks a C-alpha atom. Or, when
            the offset residue `R1_org` which maps to `R1` lacks a C-alpha. And, when the offset converted
            residue lacks a C-alpha atom.

        """
        exception_message  = ''

        if has_correctOffset is False:
            if R1 not in self.idx_with_CA:
                raise CTException("Residue index %i (where first residue = 0) lacks a C-alpha carbon" % (R1))
            return
                


        if R1 not in self.resid_with_CA:
            
            if R1_org:            
                raise CTException("Residue %i (which maps to %i) lacks a C-alpha carbon [%s]" % (R1_org, R1, self.get_amino_acid_sequence()[R1]))
            else:
                raise CTException("Residue %i (offset converted residue ID) lacks a C-alpha carbon [%s]" %(R1, self.get_amino_acid_sequence()[R1]))



    # ........................................................................
    #
    def __get_subtrajectory(self, traj, stride):
        """
        Internal function which returns a subtrajectory. Expects
        `traj` to be an `mdtraj` trajectory object and `stride` to be an `int`.

        Parameters
        ----------
        traj: mdtraj.Trajectory
            An instance of an `mdtraj.Trajectory` which is non-empty - i.e. contains
            at least 1 frame.

        stride: int
            The non-zero number of steps to perform while iterating across the input
            trajectory, `traj`.

        Returns
        -----------
        mdtraj.Trajectory
            A sliced trajectory which contains the frames selected every `stride` step
            from the input trajectory, `traj`.
              
        """

        stride = int(stride)
        self.__check_stride(stride)
        
        if stride == 1:
            return traj
        else:                                    
            return traj.slice(list(range(0, self.n_frames, stride)))            
        

    # ........................................................................
    #
    def __get_resid_with_CA(self):
        """
        Internal function which should only be needed during initialization. Defines the 
        list of residues where CA atoms are present, and the list of zero-indexed residue indices
        which contain CA atoms.

        In the case that the first resid in the self.topology object is 0 then these two lists are
        the same (which for MDTraj 1.9.5 or higher should always be the same) but for systems with
        multiple protein chains in MDTraj 1.9.4 or lower the residuesWithCA and idxWithCA willn differe
        for the second chain and onwards.
        
        
        This list is then assigned to the property variable `self.resid_with_CA` and `self.idx_with_CA`.

        Note this is quite slow for large trajectories

        Returns
        -----------
        tuple
            A 2-tuple that is comprised of lists:

            - [0] := The list of residue indices which contain C-alpha atoms selected from the topology.
            - [1] := The list of zero-indexed residue indices which contain C-alpha atoms.

        See also
        ------------
        resid_with_CA
        idx_with_CA        
              
        """
        
        # initialize empty lists
        residuesWithCA = []
        idxWithCA = []

        idx = -1

        # for each residue in the topology
        for res in self.topology.residues:
            idx = idx + 1

            # try and get the CA atomic index
            try:                
                self.get_CA_index(res.index, correctOffset=False)

                # if we could get a CA then append this residue index
                residuesWithCA.append(res.index)
                idxWithCA.append(idx)

            except CTException:
                continue

        return (residuesWithCA, idxWithCA)


    # ........................................................................
    #
    def __residue_atom_lookup(self, resid, atomname=None):
        """
        Memoisation function to lookup the atomic index of a specific residues atom. Originally I'd assumed
        the underlying MDTraj `topology.select()` operation was basically a lookup, BUT it turns out it's 
        actually *really* expensive, so this method converts atom/residue lookup information into a 
        dynamic O(1) operation, greatly improving the performance of a number of different methods
        in the processes.

        Parameters
        ----------
        resid: int
            The residue index to lookup. This index must correspond to the range derived from the corrected offset.
            If the residue has not been cached, it will be added to the lookup table for later reuse.

        atomname: str or None {None}
            The name of the atom to lookup which will return the corresponding residue ID. Like the previous parameter, 
            if that residue does not exist in the lookup table it will be added for later reuse. 

        Returns
        -------
        list
            A list containing all the atoms corresponding to a given residue id that match the input residue id (`resid`)
            or, the residue corresponding to the atom name (`atomname`).

        """

        # if resid is not yet in table, create an empty dicitionary
        if resid not in self.__residue_atom_table:
            self.__residue_atom_table[resid] = {}
        
        # if we haven't specified an atom look up ALL the atoms associated with this residue
        if atomname is None:
            
            # if all_atoms not yet associated with this residue
            if 'all_atoms' not in self.__residue_atom_table[resid]:
                self.__residue_atom_table[resid]['all_atoms'] = self.topology.select('resid %i'%(resid))

            # return set of all atoms
            return self.__residue_atom_table[resid]['all_atoms']
                                
        # if atom-name not yet associated with this resid lookup
        # the atomname from the underlying topology 
        if atomname not in self.__residue_atom_table[resid]:
            self.__residue_atom_table[resid][atomname] = self.topology.select('resid %i and name %s'%(resid, atomname))
            
        # at this point we know the resid-atomname pair is in the table
        # so goahead and look it up!
        return self.__residue_atom_table[resid][atomname]

    # ........................................................................
    #
    def __get_selection_atoms(self, region=None, backbone=True, heavy=False, correctOffset=True):
        """
        Function which returns a list of atoms associated with the residues defined by the
        region keyword. If no region is supplied this returns the entire region (NME/ACE caps
        included).

        
        Parameters
        ----------
        
        region : `np.array`, `list`, or `tuple` {None}
            An array_like object of size 2 which defines the first and last residue (INCLUSIVE) for a region to be examined.

        backbone: bool {True}
            Boolean flag to determine if only the backbone atoms should be returned, or if all the full
            chain's atoms should be included (i.e. including sidechain).

        heavy: bool {False}
            Boolean flag to determine if we should only select heavy atoms or not (i.e. not H).

        correctOffset: bool {True}
            Defines if we perform local protein offset correction or not. By default we do, but some internal functions
            may have already performed the correction and so don't need to perform it again

        Returns
        -------
        selectionatoms
            A `numpy.array` comprised of atom indices corresponding to the residues in a given region.

        Raises
        ------
        CTException
            When the input region is larger than 2.

        """

        # perform offset if necessary
        if correctOffset and not region == None:
            tmp = []
            for i in region:
                tmp.append(self.get_offset_residue(i))
            region = tmp
        
        if region is None:
            pass

        elif not len(region) == 2:
            CTException("Trying to select a subsection of atoms, but the provided 'region' tuple/list is not of exactly length two [region=%s].\nCould indicate a problem, so be safe raising an exception" % (str(region)))

        if not region == None and len(region) == 2:
            if backbone:                
                if heavy:
                    selectionatoms = self.topology.select('backbone and resid %i to %i and not type H)' % (region[0], region[1]))
                else:
                    selectionatoms = self.topology.select('backbone and resid %i to %i' % (region[0], region[1]))
            else:
                if heavy:
                    selectionatoms = self.topology.select('resid %i to %i and not type H' % (region[0], region[1]))
                else:
                    selectionatoms = self.topology.select('resid %i to %i' % (region[0], region[1]))

        else:
            if backbone:
                if heavy:
                    selectionatoms = self.topology.select('backbone and resid %i to %i and not type H' % ( self.residue_offset, self.residue_offset + self.n_residues))
                else:
                    selectionatoms = self.topology.select('backbone and resid %i to %i' % ( self.residue_offset, self.residue_offset + self.n_residues))

            else:
                if heavy:
                    selectionatoms = self.topology.select('resid %i to %i and not type H' % (self.residue_offset, self.residue_offset + self.n_residues))
                else:
                    selectionatoms = self.topology.select('resid %i to %i' % (self.residue_offset, self.residue_offset + self.n_residues))

        return selectionatoms


    # ........................................................................
    #
    def print_residues(self, verbose=True):
        """
        Function to help determine the mapping of residue ID to PDB residue value. 
        Prints the mapping between resid and PDB residue, and returns this information
        in a list.
        
        Returns a list of lists, where each list element is itself a list of two elements,
        index position and the resname-resid from the PDB file.
        

        Parameters
        ----------
        verbose : bool {True}
            If set to `True`, `print_residues()` will print out to screen and also return
            a list. If set to False, means nothing is printed to the screen.

        Returns
        -------
        return_list
            List containing a mapping of the zero-indexed residues and their names.
        """


        AA = self.get_amino_acid_sequence()
        return_list = []
        for i in range(0, len(AA)):
            if verbose is True:
                print("%i --> %s" %(i, AA[i]))
            return_list.append([i,AA[i]])
        return return_list

       
    # ........................................................................
    #        
    def get_amino_acid_sequence(self, oneletter=False, numbered=True):
        """
        Returns the protein's amino acid sequence.

        Parameters
        ----------
        oneletter : bool {False}
            If `True` returns a single sequence of one letter amino
            acid codes. If `False` get a list of 3 letter codes with residue 
            number separated by a '-' character.

        numbered : bool {True}
            If `True` the return value is a list of RESNAME-RESID strings, 
            if `False` return value is a list of RESNAME in the correct order.

        Returns
        -------
        list
            A list comprised of the 1-letter or 3-letter names of the amino acid
            sequence.
        """
        
        if oneletter:

            if self.__amino_acids_1LTR == None:
                res = []
                for i in self.topology.residues:
                    res.append(THREE_TO_ONE[str(i)[0:3].upper()])
                self.__amino_acids_1LTR = "".join(res)

        else:
            
            if self.__amino_acids_3LTR == None:
                res = []
                for i in self.topology.residues:
                    res.append(str(i)[0:3]+"-"+str(i)[3:])
                self.__amino_acids_3LTR = res

        # if numbered requsted
        if numbered:
            if oneletter:
                return self.__amino_acids_1LTR
            else:            
                return self.__amino_acids_3LTR

        # else strip out the numbering with list comprehension
        else:
            if oneletter:
                return [x.split('-')[0] for x in self.__amino_acids_1LTR]
            else:
                return [x.split('-')[0] for x in self.__amino_acids_3LTR]
                
            
     

    # ........................................................................
    #
    def get_CA_index(self, residueIndex, correctOffset=True):
        """ 
        Get the CA atom index for the residue defined by residueIndex. Again does this
        via memoization - i.e. the first time a specific residue is requested the function
        looks up the information and then stores it locally in case its needed again.

        Defensivly checks for errors.

        Parameters
        ----------
        
        residueIndex: int
            Defines the residue index to select the CA from.

        correctOffset: bool {True}
            Defines if we perform local protein offset correction
            or not. By default we do, but some internal functions
            may have already performed the correction and so don't
            need to perform it again.

        Returns
        -------
        list
            A list of size 1 containing the CA atom index for the residue index, `residueIndex`.

        Raises
        ------
        CTException
            When the number of CA atoms do not equal 1.

        """
                
        # perform offset if necessary 
        if correctOffset:
            residueIndex = self.get_offset_residue(residueIndex)

        if residueIndex not in self.__CA_residue_atom:            
            return_val = self.__residue_atom_lookup(residueIndex, 'CA')
        
            if len(return_val) == 1:
                self.__CA_residue_atom[residueIndex] = return_val[0]            
            else:
                raise CTException("get_CA_index - unable to find residue %i [corrected resid]" % residueIndex)
        
        return self.__CA_residue_atom[residueIndex] 


    # ........................................................................
    #
    def get_multiple_CA_index(self, resID_list=None, correctOffset=True):
        """
        Returns the atom indices associated with the C-alpha (CA) atom for the
        residues defined in the resID_list OR for all residues, if no list 
        is provided.

        Parameters
        ----------
        
        resID_list: list of int  {None}
            Defines a list of residues for which the C-alpha atom index will 
            be retrieved. If no list is provided we simply select the list
            of residues with C-alphas, whose indices have been corrected.

        correctOffset: bool {True}
            Defines if we perform local protein offset correction
            or not. By default we do, but some internal functions
            may have already performed the correction and so don't
            need to perform it again.
        
        Returns
        -------
        CAlist: list
            The list (`int`) of C-Alpha indices of the input list of residue IDs.
        """

        # if we've just passed a single unlisted integer
        # then just return the single residue associated 
        # with
        if type(resID_list) == int:
            return ([self.get_CA_index(resID_list, correctOffset)])

        # if no value passed grab all the residues
        if resID_list == None:

            # this list uses corrected residue index positions. Note now the
            # correctOffset flag is irrelevant because we didn't pass any 
            # positions to offset!
            resID_list = self.resid_with_CA

        else:
            if correctOffset:
                tmp = []
                for resid in resID_list:
                    tmp.append(self.get_offset_residue(resid))
                resID_list = tmp
            
        CAlist = []
        for res in resID_list:
            try:
                CAlist.append(self.get_CA_index(res, correctOffset=False))
            except CTException as e:                
                print(e)
                continue
        
        return CAlist


        
    # ........................................................................
    #
    def calculate_all_CA_distances(self, residueIndex,  mode='CA', onlyCterminalResidues=True, correctOffset=True, stride=1):
        """
        Calculate the full set of distances between C-alpha atoms. Note that by default 
        this explicitly works in a way to avoid computing redundancy where we ONLY
        compute distances between residue `i` and residues greater than `i` up
        to the final residue. This behaviour is defined by the `onlyCterminalResidues` flag.

        Distance is returned in Angstroms.

        Can be fed a mode 'COM' keyword to calcule center of mass distances instead of CA distances.

        Parameters
        ----------
        
        residueIndex: int
            Defines the residue index to select the CA from.

        mode: str {'CA'}
            String, must be one of either 'CA' or 'COM'.
            - 'CA' = alpha carbon.
            - 'COM' = center of mass (associated withe the residue).

        onlyCterminalResidues: bool {True}
            This variable means that only residues C-terminal of the residueIndex 
            value will be considered. This is useful when performing an ALL vs. ALL
            matrix as it ensures that only the upper triangle is calculated if we
            iterate over all residues, but may not be deseriable in other contexts.

        correctOffset: bool {True}
            Defines if we perform local protein offset correction
            or not. By default we do, but some internal functions
            may have already performed the correction and so don't
            need to perform it again.

        stride: int {1}
            Defines the spacing between frames to compare - i.e. if comparing frame1 to a trajectory we'd compare
            frame 1 and every stride-th frame.

        Returns
        -------
        numpy.array
            Array containing the end-to-end distance measures based on the input mode.

        Raises
        ------
        CTException
            If the input mode is nether 'CA' or 'COM'.

        """

        # validate input
        ctutils.validate_keyword_option(mode, ['CA', 'COM'], 'mode')

        # first check the residue we passed is valid and offset if required
        if correctOffset:
            residueIndex = self.get_offset_residue(residueIndex)
            
        # determine atomic index of CA atom for the residue you passed in
        try:
            CA_base = self.get_CA_index(residueIndex, correctOffset=False)
        except CTException:

            # if we couldln't find a C-alpha for this residue then nothing
            # makes sense so return -1 
            return -1
                        
        # list of atomic indices for C-alpha atoms we care about 
        CAlist = [] 

        ##
        ## Block to use if using CA as base for computing distances
        ##
        if mode == 'CA':
            for residue in self.resid_with_CA:

                # only compute distances bigger than the residueIndex
                # such that by default full iteration calculates the 
                # non-redundant map (i.e. the half diagonal)
                if residue <= residueIndex and onlyCterminalResidues:
                    continue
            
            
                # note we have the correctOffset set the false because the residue
                # index here is the true residue index as was pre-calculated
                CAlist.append(self.get_CA_index(residue, correctOffset=False))

                
                
            # now we construct a nested list of lists of pairs to compute distances
            # between
            pairs=[]
            for CA in CAlist:            
                pairs.append([CA_base, CA])

            if len(pairs) == 0:
                return np.array([])
            
                
            local_traj = self.__get_subtrajectory(self.traj, stride)

            # 10* for angstroms
            return 10*md.compute_distances(local_traj, np.array(pairs))
        if mode == 'COM':
            ##
            ## Block to use if using COM as base for computing distances
            ##
            return_distances = []
            for residue in self.resid_with_CA:
                # only compute distances bigger than the residueIndex
                # such that by default full iteration calculates the 
                # non-redundant map (i.e. the half diagonal)
                if residue <= residueIndex and onlyCterminalResidues:
                    continue

                return_distances.append(self.get_inter_residue_COM_distance(residueIndex, residue))
            
            # finally convert list to numpy array and flip so returns in same format as CA mode
            return np.array(return_distances).transpose()



    # ........................................................................
    #
    def get_distance_map(self, mode='CA', RMS=False, stride=1, weights=False, verbose=True):
        """
        Function to calculate the CA defined distance map for a protein of interest. Note 
        this function doesn't take any arguments and instead will just calculate the complete
        distance map. 
        
        NOTE that distance maps are calculated between all CA-CA distances and NOT center of 
        mass positions. This also means ACE/NME caps are EXCLUDED from this anlysis.

        Distance is described in Angstroms.

        Parameters
        ----------
        
        mode : str {'CA'}
            String, must be one of either 'CA' or 'COM'.
            - 'CA' = alpha carbon.
            - 'COM' = center of mass (associated withe the residue).

        RMS : bool {False}
            If set to False, scaling map reports ensemble average distances (this is the standard and
            default behaviour). If True, then  the distance reported is the root mean squared (RMS)
            = i.e. SQRT(<r_ij^2>), which is the formal order parameter that should be used for polymeric 
            distance properties.
                        
        stride : int {1}
            Defines the spacing between frames to compare - i.e. if comparing frame1 to a trajectory we'd compare
            frame 1 and every stride-th frame.
        
        weights : list or array of floats
            Defines the frame-specific weights if re-weighted analysis is required. This can be 
            useful if an ensemble has been re-weighted to better match experimental data, or in
            the case of analysing replica exchange data that is re-combined using T-WHAM.

        verbose : bool
            Flag that by default is True determines if the function prints status updates. This is relevant because
            this function can be computationally expensive, so having some report on status can be comforting!

        Returns
        -------
        tuple
            A 2-tuple containing:
            - [0] := The distance map derived from the measurements between CA atoms.
            - [1] := The standard deviation corresponding to the distance map.
        """

        ctutils.validate_keyword_option(mode, ['CA', 'COM'], 'mode')
        
        weights = self.__check_weights(weights, stride)
        
        # get the list of residues which have CA (typically this means we exclude
        # ACE and NME if they're present, but they may not be                        
        residuesWithCA = self.resid_with_CA

        # initialize empty matrices that we're gonna fill up
        distanceMap = np.zeros([len(residuesWithCA),len(residuesWithCA),])
        stdMap = np.zeros([len(residuesWithCA),len(residuesWithCA),])
                
        SM_index=0
        for resIndex in residuesWithCA[0:-1]:


            ctio.status_message("On protein residue %i (overall residue index = %i) of %i [distance calculations]"% (SM_index, resIndex, int(len(residuesWithCA))), verbose)

            # get all CA-CA distances between the residue of index resIndex and every other residue. Note this gives the non-redudant upper 
            # triangle. No need to correct for offset because this was done when we retrived the set of residues with CA
            full_data = self.calculate_all_CA_distances(resIndex, mode=mode, stride=stride, correctOffset=False)    

            # if we want root mean square then NOW square each distances
            if RMS:
                full_data = np.power(full_data,2)
            
            # calculate mean and standard deviation
            if weights is not False:

                mean_data = np.average(full_data,0,weights=weights)

                # if we want RMS then NOW take square root of <rij^2> 
                if RMS:
                    mean_data = np.sqrt(mean_data)
                std_data  = None
            else:

                mean_data = np.mean(full_data,0)
                
                # if we want RMS then NOW take square root of <rij^2> 
                if RMS:
                    mean_data = np.sqrt(mean_data)

                std_data = np.std(full_data,0)

            # update the maps appropriately and increment the counter
            distanceMap[SM_index][1+SM_index:len(residuesWithCA)] = mean_data
            stdMap[SM_index][1+SM_index:len(residuesWithCA)] = std_data            

            SM_index=SM_index+1

        return (distanceMap, stdMap)


    # ........................................................................
    #
    def get_polymer_scaled_distance_map(self, nu=None, A0=None, min_separation=10, mode='fractional-change', stride=1, weights=False, verbose=True):
        """
        Function that allows for a global assesment of how well all `i-j` distances conform to standard
        polymer scaling behaviour (i.e. $r_ij = A0*|i-j|^{nu}$).

        Essentially, this generates a distance map (2D matrix of i vs. j distances) where that distance is either 
        normalized by the expected distance for a provided homopolymer model, or quantifies the fractional deviation
        from a homopolymer model fit to the data. These two modes are explained in more detail below.

        In this standard scaling relationship:

        `r_ij`  : Average inter-residue distance of residue i and j

        `A0`    : Scaling prefactor. Note this is NOT the same *numerical* value as the R0 prefactor that
                defines the relationship Rg = R0*N^{nu}.

        `|i-j|` : Sequence separation between residues i and j

        `nu`    : The intrinsic polymer scaling exponent

        This is the scaling behaviour expected for a standard homopolymer. This function then assess how well
        this relationship holds for ALL possible inter-residue distances.

        This function returns a four position tuple. Position 1 is an n x n numpy matrix (where n = sequence length), 
        where the element is either the default value OR quantifes the deviation from a polymer model in one of two ways.
        Positions two and three are the nu and A0 values used, respectively. Finally, position 4 will be the reduced chi-square
        fitting to the polymer model for the internal scaling profile (i.e. how A0 and nu are originally calculated). NOTE
        that the reduced chi-squared value will be -1 if nu and A0 are provided manually.

        If no options are provided, the function calculates the best fit to a homopolymer mode using the 
        default parameters associated with the get_scaling_exponent() function, and then uses this
        model to determine pairwise deviations.
        
        Parameters
        ----------

        nu : float {None}
            Scaling exponent used (if provided). Note for a provided nu to be used, both nu and A0 must be
            provided.

        A0 : float {None}
            Scaling prefactor used (if provided). Note for a provided A0 to be used, both A0 and nu must be
            provided.

        min_separation : int {10}
            Minimum distance for which deviations are calculated. At close distances, we expect local steric
            effects to cause deviations from a polymer model, so this value defines the threshold minimum
            distance to be used.

        mode : str {'fractional-change'}
            Defines the mode in which deviation from a homopolymer model is calculated. Options are: 
            `'fractional-change', 'signed-fractional-change', 'signed-absolute-change', 'scaled'`.
            
            *fractional-change:*
            Each inter-residue deviation is calculated as
                `d_ij = abs(r_ij - polymer_ij)/polymer_ij`
            Where r_ij is the mean distance from the simulation for residues i and j, and 
            polymer_ij is the expected distance for any pair of residues that are separated
            by `|i-j|` distance in the polymer model.

            *signed-fractional-change:* 
            Each inter-residue deviation is calculated as:       
                `d_ij = (r_ij - polymer_ij)/polymer_ij`
            i.e. the same as the fractional-change, except a sign is now also included. Positive
            values mean there is expansion with respect to the homopolymer behaviour, while
            negative values mean there is contraction with respect to the homopolymer model.

            *signed-absolute-change:* 
            Each inter-residue deviation is calculated as:       
                `d_ij = (r_ij - polymer_ij)`
            i.e. the same as the signed-fractional-change, except now it is no longer 
            fraction but in absolute distance units. This can be useful for getting a 
            sense of by how-much the real behaviour deviates from the model in terms
            of Angstroms.

            *scaled:* 
            Each inter-residue deviation is calculated as:       
                `d_ij = r_ij/polymer_ij`
            Where `r_ij` is and `polymer_ij` are defined as above.
        
        weights : list or array of floats {None}
            Defines the frame-specific weights if re-weighted analysis is required. This can be 
            useful if an ensemble has been re-weighted to better match experimental data, or in
            the case of analysing replica exchange data that is re-combined using T-WHAM.

        verbose : bool
            Flag that by default is True determines if the function prints status updates. This is relevant because
            this function can be computationally expensive, so having some report on status can be comforting!

        Returns
        -------
        tuple (len = 4)

            return[0]  : n x n numpy matrix (where n = sequence length), where the element is either the default value 
                         OR quantifes the deviation from a polymer model in one of two ways.
           

            return[1]  : float defining the scaling exponent nu

            return[2]  : float defining the A0 prefactor

            return[3]  : reduced chi-squared fitting to the polymer model (goodness of fit)

        Raises
        ------
        CTException
        
        """
        
        # First validate keyword
        ctutils.validate_keyword_option(mode, ['fractional-change','scaled', 'signed-fractional-change', 'signed-absolute-change'], 'mode')

        # next check that the minimum separation requested makes sense... (this is only a partial check)
        if min_separation < 1:
            raise CTException("Minimum separation to be used must be greater than 0")
                        
        ## next see if nu or A0 have been provided...

        # If NEITHER provided then do fitting here and now!
        if nu == None and A0 == None:
            ctio.status_message("Fitting data to homopolymer mode...", verbose)

            # remind that this is the old get_scaling_exponent_v2() 
            # ALSO note this uses COM which is also how the distance map is computed
            SE = self.get_scaling_exponent(verbose=False, weights = weights, stride = stride)
            nu = SE[0]
            A0 = SE[1]
            REDCHI = SE[7]
            
        elif nu is None:
            raise CTException("A0 parameter provided [%1.5f] but nu was not. Must provide BOTH or neither (in which case fitting is done)" %( A0))

        elif A0 is None:
            raise CTException("nu parameter provided [%1.5f] but A0 was not. Must provide BOTH or neither (in which case fitting is done)" %( nu))

        # else both were provided so we double check they're valid..
        else:
            # sanity check nu
            if nu <= 0 or nu > 1:
                raise CTException("Nu parameter must be in interval 0 < nu <= 1 (and probably should be between 0.33 and 1.0...)")

            # sanity check A0
            if A0 <= 0:
                raise CTException("A0 paameter must be greater than 0")

            # not computing a reduced chi
            REDCHI = -1
            
        # We now define a function which will evaluate how we assess the deviation (or lack thereof) from the 
        # traditional polymer scaling behaviour. This just saves us having if/then statements that get evaluated
        # on each loop of the analysis script below, and also makes it easy to add in additional 'modes'

        if mode  == 'fractional-change':
            def d_funct(dMap_val, p_val):
                return abs(dMap_val - p_val)/p_val

            default_val = 0 

        elif mode == 'signed-fractional-change':
            def d_funct(dMap_val, p_val):
                return (dMap_val - p_val)/p_val

            default_val = 0 

        elif mode == 'signed-absolute-change':
            def d_funct(dMap_val, p_val):
                return (dMap_val - p_val)

            default_val = 0 

        elif mode == 'scaled':
            def d_funct(dMap_val, p_val):
                return dMap_val/p_val

            default_val = 1

        ## Now we've set everything up we can actually compute some numbers

        # first compute and get the distance map (note [0] means we get first element
        # which is mean distance ([1] is STDEV)
        distance_map = self.get_distance_map(mode='COM', RMS=True, stride=stride, weights=weights, verbose=False)[0]

        # get distance map dimensions (will be a square so just take X-dim)
        dimensions = distance_map.shape[0]

        if dimensions <= min_separation:
            raise CTException('The minimum separation is shorter than the chain length')

        # compute expected distance given the standard polymer scaling model
        expected_distances = cttools.powermodel(list(range(0,dimensions)), nu, A0)

        # initialize the return matrix and then populate for distances that are
        # above the minimum threshold. We only populate upper right triangle
        return_matrix = np.zeros((dimensions, dimensions))
        for i in range(0,dimensions):
            for j in range(0,dimensions):
                if j-i < min_separation:
                    return_matrix[i,j] = default_val
                else:                    
                    return_matrix[i,j] = d_funct(distance_map[i,j], expected_distances[(j-i)])

        return (return_matrix, nu, A0, REDCHI)

    # ........................................................................
    #
    def get_local_heterogeneity(self, fragment_size=10, bins=None, stride=20, verbose=True):
        """
        Function to calculate the vector of D values used to calculate the Phi parameter from Lyle et al[1].
        The stride defines the spacing between frames which are analyzed. This is just for practical purposes.
        The Phi calulation computes a D value for each frame vs. frame comparison - for a 2000 frame simulation
        this would be 4 Million D values if every value was calculated which is a bit much, so the stride let's
        you define how many frames you should skip. 
        
        For a 2000 frame trajectory of a 80 residue protein with a stride=20 allows the calculation to take 
        about 5 seconds. However, as protein size increases the computational cost of this process grows
        rapidly.


        Parameters
        -----------
        
        fragment_size : int {10}        
            Size of local region that is considered to be a single unit over which structural heterogeneity
            is examined. Should be between 2 and the length of the sequence.

        bins : np.ndarray {np.arange(0,1,0.01)}
            Bins used to capture the heterogeneity at each position. If default a set of bins from 0 to 1 with an
            interval of 0.01 is used

        stride : int {20}
            Defines the spacing between frames to compare - i.e. if comparing frame1 to a trajectory we'd compare
            frame 1 and every stride-th frame.

        verbose : bool
            Flag that by default is True determines if the function prints status updates. This is relevant because
            this function can be computationally expensive, so having some report on status can be comforting!

        
        Returns
        -------
        tuple (len = 4)

            return[0]  : list of floats of len *n*, where each float reports on the mean RMSD-deviation at a specific 
                         position along the sequence as defined by the fragment_size

            return[1]  : list of floats of len *n* , where each float reports on the standard deviation of the 
                         RMSD-deviation  at a specific position along the sequence as defined by the fragment_size

            return[2]  : List of np.ndarrays of len *n*, where each sub-array reports on the histogram values associated
                         with the full RMSD distribution at a given position along the sequence

            return[3]  : np.ndarray which corresponds to bin values for each of the histograms in return[2]

        Raises
        ------
        CTException


        """

        # validate bins
        if bins is None:
            bins = np.arange(0,10,0.01)
        else:
            try:
                if len(bins)  < 2:
                    raise CTException('Bins should be a numpy defined vector of values - e.g. np.arange(0,1,0.01)')                    
            except TypeError:
                raise CTException('Bins should be a list, vector, or numpy array of evenly spaced values')

            try:
                bins = np.array(bins, dtype=float)
            except ValueError:
                raise CTException('Passed bins could not be converted to a numpy array of floats')
                
        # check stride is ok
        self.__check_stride(stride)

        # get the residue IDXs were going to use
        res_idx_list = self.residue_index_list
        n_frames = self.n_frames

                            
        # check the fragment_size is appropriate
        if fragment_size > len(res_idx_list):
            raise CTException('fragment_size is larger than the number of residues')
        if fragment_size < 2:
            raise CTException('fragment_size must be 2 or larger')
        

        meanData = []
        stdData  = []
        histo    = []
        
        # cycle over each sub-region in the sequence
        for frag_idx in res_idx_list[0:-fragment_size]:
            tmp = []
            ctio.status_message("On range %i" % frag_idx, verbose)

            # for each frame in ensemble, calculate RMSD for that sub-region compared to
            # all other sub-regions (i.e. we're doing a 1-vs-all RMSD calculation for EACH
            # frame (after adjusting for stride) for a subregion of the protein
            for j in range(0, n_frames, stride):
                tmp.extend(self.get_RMSD(j ,-1, region=[frag_idx, frag_idx+fragment_size]))
                            
            # compute a histogram for this large dataset
            (b,c) = np.histogram(tmp,bins)
            histo.append(b)
                                
            meanData.append(np.mean(tmp))
            stdData.append(np.std(tmp))

        return (meanData, stdData, histo, bins)
        


    # ........................................................................
    #
    def get_D_vector(self, stride=20, verbose=True):
        """
        Function to calculate the vector of D values used to calculate the Phi parameter from Lyle et al[1].

        The stride parameter defines the spacing between frames which are analyzed. This is just for practical 
        purposes.

        The Phi calulation computes a D value for each frame vs. frame comparison - for a 2000 frame simulation
        this would be 4 Million D values if every value was calculated which is a bit much, so the stride let's
        you define how many frames you should skip. 

        Importantly, the DVector calculated here measures dij (see part III A of the paper) as the CA-CA distance
        and NOT the average inter-atomic distance. This has two effects: 

        1) Heterogeneity is now, formally, a measure over backbone heterogeneity and not full protein heterogeneity
           - this may be desirable (arguably it's a more interpratable measure of conformational change) but if the
           interatomic version is required this could be implemented.

        2) It is *much* more efficient than the original version
        
        For a 2000 frame trajectory of a 80 residue protein with a stride=20 allows the calculation to take 
        about 5 seconds. However, as protein size increases the computational cost of this process grows
        rapidly.

        Parameters
        ------------        
        stride : int {20}        
            Defines the spacing between frames to compare - i.e. if comparing frame1 to a trajectory 
            we'd compare frame 1 and every stride-th frame

        verbose : bool
            Flag that by default is True determines if the function prints status updates. This is relevant because
            this function can be computationally expensive, so having some report on status can be comforting!

        Returns
        ---------
        np.ndarray
            Returns a numpy array of D values (i.e. the D_vector)

        References
        --------------
        [1] Lyle, N., Das, R. K., & Pappu, R. V. (2013). A quantitative measure for protein conformational 
        heterogeneity. The Journal of Chemical Physics, 139(12), 121907.

        """
                
        # get the list of residues which have CA (typically this means we exlcude
        # ACE and NME)
        residuesWithCA = self.resid_with_CA

        # compute number of frames exactly (this is empyrical but ensures we're always consistent with the projected
        # dimensions in the first for-loop)
        tmp = self.calculate_all_CA_distances(residuesWithCA[0], stride=stride, onlyCterminalResidues=True, correctOffset=False)                                 
        n_frames =  np.shape(tmp)[0]
        
        all_distances = np.zeros([len(residuesWithCA),len(residuesWithCA), n_frames])
                
        # first compute upper triangle only (lower traingle is identical and doesn't change the answer
        # so we stick with the upper traingle only)
        SM_index=0
        for resIndex in residuesWithCA[0:-1]:        
            ctio.status_message("Calculating non redundant distance for res. %i " % resIndex, verbose)

            vals = self.calculate_all_CA_distances(resIndex, stride=stride, onlyCterminalResidues=True, correctOffset=False)                                 

            # have to include a -1 here because we don't have a self:self distance
            all_distances[SM_index][0:(len(residuesWithCA)-1)-SM_index] = vals.transpose()
            SM_index=SM_index+1
        
        # number of residues we're calculating distances between
        n_res = np.shape(all_distances)[0]

        # reshape to n_frame x n_rij 2D array
        all_distance_tmp = all_distances.transpose().reshape(n_frames,n_res*n_res)

        # find the idx of non-zero elements in the first frame (will be true for all frames - zeros
        # originate because we only computed the upper triangle, so 1/2 of elements in each row of
        # all_distance_tmp are zero
        non_zero_idx = np.nonzero(all_distance_tmp[0])[0]

        # finally extract out the positions that are nonzero, setting us up for the phi analysis
        non_zero_distance = all_distance_tmp[:,non_zero_idx]
        
        # calculate the D-vector of all frames
        D_vector = []
        for A in range(0, n_frames):
            ctio.status_message("Running PHI calculation on frame %i of %i" % (A, n_frames), verbose)

            
            for B in range(A+1, n_frames):
                
                """
                # This is the old less efficient implementation of the algorithm, kept in case,
                # for some reason, the new implementation has issues...

                # get the vector of distances for frame A and frame B - this extracts all the
                # inter-residue distances for frame A and frame B
                VA = all_distances.transpose()[A].flatten()
                VB = all_distances.transpose()[B].flatten()

                # remove zero entries (all real distances MUST be greater
                # than zero because there's a hardsphere potential stopping things actually
                # reaching zero distance (distance is center-of-mass calculated for Ca)
                
                # we need to calculate the allowed set 
                NZ_A = np.nonzero(VA)[0]
                NZ_B = np.nonzero(VB)[0]
                
                # this finds the positions that in both vectors were non-zero        
                all_zero = np.intersect1d(NZ_A, NZ_B)
                                        
                # now for those positions extract a new length-match vector for frame
                # A and B that contains only non-zero positions
                VA = VA[all_zero]
                VB = VB[all_zero]
                """

                VA = non_zero_distance[A]
                VB = non_zero_distance[B]

                # and compute the D value for comparing these two frames
                D_vector.append(1 - np.dot(VA,VB)/(np.linalg.norm(VA)*np.linalg.norm(VB)))
                
        return np.array(D_vector)


    # ........................................................................
    #
    def get_RMSD(self, frame1, frame2=-1, region=None, backbone=True, correctOffset=True, stride=1):
        """
        Function which will calculate the aligned RMSD between two frames, or between one frame and 
        all frames in the trajectory. This can be done over the entire protein but we can also
        specificy a local region to perform this analysis over.

        Units are Angstroms.
        

        Parameter
        --------------
        frame1 : int
            Defines the frame to be used as a reference

        frame2 : int {-1}         
            Defines the frame to be used as a comparison, OR if left blank or set to -1 means the entire 
            trajectory

        region : list/tuple of length 2  {None}
            Defines the first and last residue (INCLUSIVE) for a region to be examined. By default is set 
            to None which means the entire protein is used
        
        backbone : bool  {True}
            Boolean flag for using either the full chain or just backbone. Generally backbone alone 
            is fine so default to True.

        correctOffset : bool  {True}
            Defines if we perform local protein offset correction or not. By default we do, but some 
            internal functions may have already performed the correction and so don't need to perform it 
            again

        stride : int {1}
            Defines the spacing between frames to compare - i.e. if comparing frame1 to a trajectory we'd compare
            frame 1 and every stride-th frame
        

        Returns
        ----------
        np.ndarray
            Returns a numpy array of either 1 (if two frames are passed) or nframes length which corresponds
            to the RMSD difference either between two frames or between one frame and ALL other frames

        """

        # get the selection atoms (perform correction if required)
        selectionatoms = self.__get_selection_atoms(region=region, backbone=backbone, correctOffset=correctOffset)
            
        # set the reference trajectory we're working with
        ref = self.traj

        # if a second frame number was provided with which we're going to work with
        if frame2 > -1 and isinstance( frame2, int ):            

            # our target is now a single (i.e. doing RMSD of two structures)
            target = self.traj.slice(frame2)
        else:

            # else we're going to carry out an RMSD comparison between *every* stride-th
            # frame and frame 1
            target = self.__get_subtrajectory(self.traj, stride)

        # return the RMSD comparison in Angstroms
        return 10*md.rmsd(target, ref, frame1, atom_indices=selectionatoms)


    # ........................................................................
    #
    def get_Q(self, 
              protein_average = True, 
              region = None, 
              beta_const = 50.0,
              lambda_const = 1.8,
              native_contact_threshold = 4.5,              
              correctOffset = True, 
              stride = 1, 
              weights = False):
        """
        Function which will calculate the fraction of native contacts in each frame of the trajectory,
        where the 'native' state is defined as a specific frame (1st frame by default - note this means
        the native state frame = 0  as we index from 0!). In earlier versions the 'native state frame'
        was a variable, but this ends up being extremely messy when weights are considered, so assume
        the native state frame is always frame 0.

        Native contacts are defined using the definition from Best, Hummer, and Eaton, 
        "Native contacts determine protein folding mechanisms in atomistic simulations" 
        PNAS (2013) 10.1073/pnas.1311599110. The implementation is according to the code helpfully
        provided at http://mdtraj.org/latest/examples/native-contact.html


        Parameters
        -----------

        protein_average : bool  {True}
            This is the default mode, and means that the return vector is the AVERAGE fraction of 
            native contacts over the protein surface for each frame (e.g. each value refers to a             
            single frame). If set to false the simulation-average value at native-contact resolution is 
            returned, instead returning $NATIVE_CONTACT number of values and an additional list of native 
            contact pairs.

        region : list/tuple of length 2  {None}
            Defines the first and last residue (INCLUSIVE) for a region to be examined. By default is set 
            to None which means the entire protein is used

        beta_const : float {50}
            Constant used for computing Q in reciprocal nanometers. Default is 50 and probably should
            not be changed without good reason.

        lambda_const : float {1.8} 
            Constant value is 1.8 for all-atom simulations. Probably should not be changed without good
            reason

        native_contact_threshold : float {4.5}
            Threshold in Angstroms typically used for all-atom simulations and again probably should not
            be changed without good reason

        correctOffset : bool  {True}
            Defines if we perform local protein offset correction or not. By default we do, but some 
            internal functions may have already performed the correction and so don't need to perform it 
            again

        stride : int {1}
            Defines the spacing between frames to compare - i.e. if comparing frame1 to a 
            trajectory we'd compare frame 1 and every stride-th frame.
        
        weights : list or array of floats  {False}
            Defines the frame-specific weights if re-weighted analysis is required. This can be 
            useful if an ensemble has been re-weighted to better match experimental data, or in
            the case of analysing replica exchange data that is re-combined using T-WHAM.


        Returns
        -----------
        If protein_average=True a single vector is returned with the overall protein average fraction of 
        native contacts associated with each frame for each residue. If protein_average is set to False a 
        4-position tuple is returned, where each of the four positions has the following identity:
                 
        idx | 
        0   | The fraction of the time a contact is native for all each native contact (vector of length 
              $N_NATIVE CONTACTS)
        
        1   | The native contact definition (same length as 1) where each element is a pair of atoms which 
              are considered native              

        2   | The residue-by-residue dictionary-native contacts dictionary. Keys are residue name-number 
              and each key-associated value is the fractional native contacts for atoms associated with 
              that residue. To get the residue-specific fraction of native contacts take the mean of the 
              element values

        3   | The ordered list of keys from 2 for easy plotting in a residue-residue manner

        4   | A nres x nres array showing a 2D contact map defining inter-residue specific Q values

       
        """
        
        # SET
        native_state_frame = 0
        n_res = self.n_residues

        # less stringent weights test cos trajectory is one frame too long because we probably loaded the PDB file
        # as a frame
        #weights = self.__check_weights(weights, stride)
        
        if weights is not False and stride != 1:
            raise CTException('For get_Q() weights must be set for EACH frame and stride=1')
        
        # if we're using a subregion 
        # NOTE this is WAY more elegant than the previous way of doing this but there *used* to be problems with MDTraj doing
        # things like this...
        selectionatoms = self.__get_selection_atoms(region, backbone=False, heavy=True, correctOffset=correctOffset)
        
        # extract out the native state frame
        native = self.traj.slice(native_state_frame)

        # get the sub-trajectory to be used         
        target = self.__get_subtrajectory(self.traj, stride)

        # now align the entire trajectory to the 'native' frame
        target.superpose(target, frame=native_state_frame, atom_indices=selectionatoms)
        
        try:
            BETA_CONST = float(beta_const)       # in reciprocal nm (1/nm)        
            LAMBDA_CONST = float(lambda_const)    # For all-atom simulations

            # Native contact threshold distance in nm (not param is passed in Angstroms but the calculation
            # happens expecting nanometers so have to update (hence divide by 10)
            NATIVE_CUTOFF = float(native_contact_threshold)/10
            
        
        except ValueError as e:
            raise CTException('Could not convert constant into float for setting constants in get_Q().\nSee below:\n\n%s' % (str(e)))
            

        # use all pairs of atoms that are over 3 away in sequence space
        heavy_pairs = np.array(
            [(i,j) for (i,j) in combinations(selectionatoms, 2)
             if abs(native.topology.atom(i).residue.index - \
                    native.topology.atom(j).residue.index) > 3])
        
        # compute the distances between these pairs in the native state
        heavy_pairs_distances = md.compute_distances(native[0], heavy_pairs)[0]
            
        # and get the pairs s.t. the distance is less than NATIVE_CUTOFF. This returns the 
        # set of interatomic residues that define the native contacts
        native_contacts = heavy_pairs[heavy_pairs_distances < NATIVE_CUTOFF]

        # now compute these distances for the whole trajectory
        r = md.compute_distances(target, native_contacts)
        
        # and recompute them for just the native state
        r0 = md.compute_distances(native[0], native_contacts)

        # If we're just computing the protein average then this returns the Q value for the whole protein on a per-frame basis
        if protein_average:         
            if weights is not False:
                raise CTException('Reweighting for frame averaged should be done with trajectory weights OUTSIDE of CTraj')
                
            q = np.mean(1.0 / (1 + np.exp(BETA_CONST * (r - LAMBDA_CONST * r0))), axis=1)

            return q

        else:
            
            # if the analysis is to be re-weighted uses the weights here on a per-frame basis
            if weights is not False:
                q_full = (1.0 / (1 + np.exp(BETA_CONST * (r - LAMBDA_CONST * r0)))).transpose()

                q = []
                for i in q_full:

                    # note i[1:] means we ignore the first (native) frame
                    q.append(np.average(i[1:], 0, weights))

                q = np.array(q)
            else:

                # check this makes sense - aboe we do i[1:] should probably correct this to remove
                # the native state structure? Anyway, here we're averaging over every from for each
                # residue
                q = np.mean(1.0 / (1 + np.exp(BETA_CONST * (r - LAMBDA_CONST * r0))), axis=0)

            # get the set of unqiue atoms which are involved in native contacts
            unique_native_contact_atoms = np.unique(np.hstack((np.transpose(native_contacts)[0],np.transpose(native_contacts)[1])))

            res2at = {}
            res2res = {}

            # for each unqiue atom
            for atom in unique_native_contact_atoms:

                # determine the name of the residue it's from and update the res2at dictionary
                # if needed
                local_res = str(self.topology.atom(atom).residue)

                if local_res not in res2at:
                    res2at[local_res] = []
                    res2res[int(local_res[3:])] = local_res

                # now for every native contact pair that atom is involved in,
                # associate the fraction of the time it's native with the 
                # residue in question. 
                for pair_idx in range(0, len(native_contacts)):
                    if atom in native_contacts[pair_idx]:
                        res2at[local_res].append(q[pair_idx])

            # we now have a dictionary where, for each residue, we have the
            # ensemble average fraction of the simulation each atom was making
            # native contacts. Note different residues have different numbers
            # of atoms (obviously...) SO each entry in res2at is going to be
            # a variable length

            # now construct an n-res by n-rex empty matrix
            res_res_matrix = np.zeros((self.n_residues, self.n_residues))
            res_res_matrix_count = np.zeros((n_res, n_res))

            # and for each pair of atoms as identified previously, look up
            # which residue they're from, determine the q score for that pairwise
            # interaction, and increment the associated positions on the nres by
            # nres matrix, keeping count of how many such increments we make in the
            # res_res_matrix_count matrix
            for pair_idx in range(0,len(native_contacts)):

                pair = native_contacts[pair_idx]
                R1 = self.topology.atom(pair[0]).residue.index
                R2 = self.topology.atom(pair[1]).residue.index

                res_res_matrix[R1,R2] = q[pair_idx] + res_res_matrix[R1,R2]
                res_res_matrix[R2,R1] = q[pair_idx] + res_res_matrix[R2,R1]

                res_res_matrix_count[R1,R2] = 1 + res_res_matrix_count[R1,R2]
                res_res_matrix_count[R2,R1] = 1 + res_res_matrix_count[R2,R1]

            # finaly, pairwise division accounts for the fact that some residues
            # have more atoms than others
            normalized_res_matrix = res_res_matrix / res_res_matrix_count

            # just as a convenience, build a sorted list of the residues which makes
            # the data a bit easier to play with going forward.
            res2res_keys = list(res2res.keys())
            np.sort(res2res_keys)
            sorted_residues = []

            for lk in res2res_keys:
                sorted_residues.append(res2res[lk])

            # finally, return all the things mentioned in the function description (note we nan-to-num
            # to remove all the NaNs from the norlaized res matrix (generated by dividiving by zeor)
            return (q, native_contacts, res2at, sorted_residues, np.nan_to_num(normalized_res_matrix,0))
                    

    # ........................................................................
    #
    #
    def get_contact_map(self, distance_thresh=5.0, mode='closest-heavy', stride=1, weights=False):
        
        """
        get_contact_map() returns 2-position tuple with the  contact map (N x N matrix) and a contact order 
        vector (N x 1) that describe the contacts (heavy atom - heavy atom interactions) made by each of the 
        residues over the simulation. 
        
        Each element is normalized such that it is between 0 and 1. i+1 and i+2 elements are excluded, and 
        the minimum distances is the distance between the closest heavy atoms on each residue (backbone or         
        sidechain).

        Parameters
        -----------------
        

        distance_thresh : float {5.0}
            Distance threshold used to define a 'contact' in Angstroms. Contacts are taken as frames
            in which the atoms defined by the scheme are within $distance_thresh angstroms of one another

        mode : string  {'closest-heavy'}

            Mode allows the user to define differnet modes for computing contacts. The default value
            is 'closest-heavy'. Other options are detailed below and are identical to those offered by 
            mdtraj in compute_contacts
        
            'ca' - same as setting 'atom' and A1='CA' and A2='CA', this uses the C-alpha atoms
        
            'closest' - closest atom associated with each of the residues, i.e. the is the point
                        of closest approach between the two residues 

            'closest-heavy' - same as closest, except only non-hydrogen atoms are considered

            'sidechain' - closest atom where that atom is in the sidechain. Note this requires
                          mdtraj version 1.8.0 or higher.

            'sidechain-heavy' - closest atom where that atom is in the sidechain and is heavy. 
                                Note this requires mdtraj version 1.8.0 or higher.

        stride : int {1}
            Defines the spacing between frames to compare - i.e. if comparing frame1 to a trajectory 
            we'd compare frame 1 and every stride-th frame. Note this operation may scale poorly as 
            protein length increases at which point increasing the stride may become necessary.

        weights [list or array of floats] {False}
            Defines the frame-specific weights if re-weighted analysis is required. This can be 
            useful if an ensemble has been re-weighted to better match experimental data, or in
            the case of analysing replica exchange data that is re-combined using T-WHAM.

        Returns:
        ---------------
        tuple of size 2
            Returns a tuple where:
            0 - contact map
            1 - contact order

        
        """

        ctutils.validate_keyword_option(mode, ['closest-heavy', 'ca', 'closest', 'sidechain', 'sidechain-heavy'] , 'mode')

        if weights is not False:
            if int(stride) != 1:
                raise CTException("Cannot accomodate weighst and non-one stride")

        # check weights are correct
        weights = self.__check_weights(weights, stride)

        # set the distance threshold to a value in nm (we use A by default) 
        distance_thresh_in_nm = float(distance_thresh/10.0)
        
        # build a substractectory based on the stride argument
        subtraj = self.__get_subtrajectory(self.traj, stride)

        # ensure we only select main chain atoms (no termini) - NOTE, this is a REALLY useful design pattern - 
        # should consider re-writing the code to use this...
        mainchain_atoms = self.topology.select('(not resname NME) and (not resname ACE)')

        # compute the contactmap and square-form it (map per frame)
        # CMAP is a [N_FRAMES x N_RES x N_RES] array
        CMAP_nonsquare = md.compute_contacts(subtraj.atom_slice(mainchain_atoms), scheme=mode)
        CMAP = md.geometry.squareform(CMAP_nonsquare[0], CMAP_nonsquare[1])

        # extract the normalization factor used to compute fractional
        # contacts
        normalization_factor = np.shape(CMAP)[0]

        # build a MASK where distance is not zero (i.e. where distances were calculated
        MASK =  (CMAP[0] != 0)*1

        # if no weights...
        if weights is False:

            # for each frame set true/false if less than threshold,
            # then convert bools to ints and sum over all frames
            # and finally normalize by the normalization factor. This
            # gives us the _normalized_ contact map (i.e. each element is between 0 and 1)
            normalized_contact_map = (np.sum(1*(CMAP < distance_thresh_in_nm),0)*MASK) / float(normalization_factor)

        # else, if weights...
        else:

            # if we use weights then we multiply each frame's contact map by the weight and sum
            n_frames = CMAP.shape[0]
            normalized_contact_map = np.zeros((CMAP.shape[1],CMAP.shape[1]))
            for fid in range(0,n_frames):
                normalized_contact_map = normalized_contact_map + (np.ndarray.astype((CMAP[fid]<distance_thresh_in_nm),int)*MASK)*weights[fid]
                
        # we can further reduce the dimensionality to ask which residues are most involved in contacts with outher
        # residues in general (i.e. without caring about what those residues are). This gives us a normalized
        # contact order. 
        n_res = int(np.shape(normalized_contact_map)[0])
        
        # So this is a kind of funky line, but basically because we don't calculate over distances that are 
        # that are
        # i to i
        # i to i-1
        # i to i-2
        # i to i+1
        # i to i+2
        # which means for MOST residues the max possible is n_res-5, but for those at the end and start
        # there is no i-1/i-2 for the 0th residues, so the line below builds a vector that for each residues
        # calculates the TRUE max fractional contacts 
        contact_order_normalization_vector = n_res - np.hstack((np.hstack(([3,4],np.repeat(5,n_res-4))),[4,3]))

        normalized_contact_order = np.sum(normalized_contact_map,0)/contact_order_normalization_vector

        return (normalized_contact_map, normalized_contact_order)

                                  
                
    # ........................................................................
    #
    #
    def get_clusters(self, region=None, n_clusters=10, backbone=True, correctOffset=True, stride=20):
        """
        Function to determine the structural clusters associated with a trajectory. 
        This can be useful for identifying the most populated clusters. This approach
        uses Ward's hiearchical clustering, which means we must define the number of
        clusters we want a-priori. Clustering is done using RMSD - BUT the approach 
        taken here would be easy to re-implement in another function where you
        'simiarity' metric was something else. 

        Returns a 4-place tuple with the following sub-elements:

        [0] - cluster_members:
        A list of length n_clusters where each element corresponds to the number
        of frames in each of the 1-n_clusters cluster. i.e. if I had defined n_clusters=3
        this would be a list of length 3

        [1] - cluster_trajectories:
        A list of n_cluster mdtraj trajectory objects of the conformations in the cluster.
        This is particularly useful because it means you can perform any arbitrary analaysis
        on the cluster members

        [2] - cluster distance_matrices:
        A list of n_clusters where each member is a square matrix that defines the structural
        distance between each of the members of each cluster. in other words, this quantifies
        how similar (in terms of RMSD, in units Angstroms).
        
        [3] - cluster_centroids
        A list of n_clusters where each element is the index associated with each cluster
        trajectory that defines the cluster centroid (i.e. a 'representative' conformation).
        As an example - if we had 3 clusters this might look like [4,1,6], which means the
        4th, 1st, and 6th frame from each of the respective mdtraj trajectories in the
        cluster_trajectories list would correspond to the centroid.

        [4] - cluster frames:
        List of lists, where each sublist contains the frame indices associated with
        that cluster. Useful if clustering on a single chain and want to use that
        information over an entire trajectory
        
        ........................................
        OPTIONS 
        ........................................
        region [list/tuple of length 2]  {[]}
        Defines the first and last residue (INCLUSIVE) for a region to be examined

        n_clusters [int] {10}
        Number of clusters to be returned through Ward's clustering algorithm. 

        backbone [bool] {True}
        Flag to determine if backbone atoms or full chain should be used

        correctOffset [Bool] {True}
        Defines if we perform local protein offset correction
        or not. By default we do, but some internal functions
        may have already performed the correction and so don't
        need to perform it again.

        stride [int] {20}     
        Defines the spacing betwen frames to compare with - i.e. take every $stride-th frame.
        Setting stride=1 would mean every frame is used, which would mean you're doing an
        all vs. all comparions, which would be ideal BUT may be slow.


        """

        # build an empty distance matrix
        if self.n_frames % stride == 0:
            distance_dims = int(self.n_frames/stride)
        else:
            distance_dims = int((self.n_frames/stride))+1

        distances = np.zeros((distance_dims, distance_dims))
        
        idx=0

        # build an all vs. all RMSD matrix based on the parameters provided for every
        # stride-th frame
        for i in range(0,self.n_frames,stride):
            distances[idx] = self.get_RMSD(i, stride=stride, region=region, backbone=backbone, correctOffset=correctOffset)
            idx=idx+1

        # CLUSTERING
        # having computed the RMSD distance matrix we do Ward based hierachical clustering 
        # and then separate out into n_clusters
        
        # we feed ward a redundant distance matrix
        # See: http://docs.scipy.org/doc/scipy/reference/generated/scipy.cluster.hierarchy.ward.html#scipy.cluster.hierarchy.ward
        linkage = scipy.cluster.hierarchy.ward(distances)

        # linkage is the hierachical clustering encoded as a linkage matrix
        labels = scipy.cluster.hierarchy.fcluster(linkage, t=n_clusters, criterion='maxclust')

        # get a subtrajectory which corresponds to the trajectory examined
        # in the all vs. all comparison (i.e. a trajectory made of every stride-th
        # frame
        subtraj = self.__get_subtrajectory(self.traj, stride)

        # if we're looking at a region further extract out ONLY the atoms
        # associated with that subregion
        if region is not None:
            selectionatoms = self.__get_selection_atoms(region, backbone)
            subtraj = subtraj.atom_slice(selectionatoms)
                        
        # we now build n_cluster separate trajectories contaning conformations from the clustering
        cluster_trajs = []
        cluster_distance_matricies = []
        cluster_centroids = []
        cluster_members = []
        cluster_frames = []

        # regardless of how many clusters we *think* we should have, extract the number of labeles
        # we'll actually have...
        final_labels = list(set(labels))
        # for each cluster
        for i in final_labels:

            # determine the indices associated with frames which are associated 
            # with the i-th cluster
            IDXs=np.where(labels == i)
            IDXs=IDXs[0]
            cluster_frames.append(IDXs)

            # record how many frames are associated with the i-th cluster
            cluster_members.append(len(IDXs))

            # create the trajectory and append to the cluster_trajectory list
            cluster_trajs.append(subtraj.slice(IDXs))
            
            # create the appropriate submatrix
            cluster_distances=np.zeros((len(IDXs), len(IDXs)))

            # initial distances is a subset of the all vs all RMSD distance
            # matrix which now only includes rows associated with the frames
            # from the i-th cluster
            initial_dist=distances[IDXs]

            # for each frame associated with the i-th cluster
            for k in range(0,len(IDXs)):

                # add the full all vs. all set of distances between each of the frames from
                # the i-th cluster and all the other frames from the i-th clster 
                cluster_distances[k] = initial_dist[k][IDXs]

            # at this point the cluster_distances matrix is an all vs. all RMSD distance
            # matrix for all the frames in i-th cluster - this effectivly gives you a way
            # to think about how well an RMSD cluster represents those structures
            cluster_distance_matricies.append(cluster_distances)
            
            # we determine the frame closest to the centroid of the cluster
            cluster_centroids.append(np.exp(-1*cluster_distances / cluster_distances.std()).sum(axis=1).argmax())
        
        return (cluster_members, cluster_trajs, cluster_distance_matricies, cluster_centroids, cluster_frames)


    # ........................................................................
    #
    #
    def get_inter_residue_COM_distance(self, R1, R2, correctOffset=True, stride=1):
        """
        Function which calculates the complete set of distances between two residues'
        centers of mass (COM) and returns a vector of the distances.

        Distance is returned in Angstroms.

        ........................................
        OPTIONS 
        ........................................
        R1 [int]
        Residue index of first residue

        R2 [int] 
        Residue index of second residue

        correctOffset [Bool] {True}
        Defines if we perform local protein offset correction
        or not. By default we do, but some internal functions
        may have already performed the correction and so don't
        need to perform it again.

        stride [int] {1}     
        Defines the spacing betwen frames to compare with - i.e. take every $stride-th frame.
        Setting stride=1 would mean every frame is used, which would mean you're doing an
        all vs. all comparions, which would be ideal BUT may be slow.


        """

        # first check that the residues we're working with make sense
        if correctOffset:
            R1 = self.get_offset_residue(R1)
            R2 = self.get_offset_residue(R2)
        else:
            R1 = int(R1)
            R2 = int(R2)

        
        # get COM of the two residues for every stride-th frame (only split
    
            
        if R1 not in self.__residue_COM:
            atoms1 = self.__residue_atom_lookup(R1)
            TRJ_1 = self.traj.atom_slice(atoms1)        
            TRJ_1 = self.__get_subtrajectory(TRJ_1, stride) 
            self.__residue_COM[R1] = md.compute_center_of_mass(TRJ_1)
        

        if R2 not in self.__residue_COM:
            atoms2 = self.__residue_atom_lookup(R2)
            TRJ_2 = self.traj.atom_slice(atoms2)        
            TRJ_2 = self.__get_subtrajectory(TRJ_2, stride) 
            self.__residue_COM[R2] = md.compute_center_of_mass(TRJ_2)
            
        COM_1 = self.__residue_COM[R1]
        COM_2 = self.__residue_COM[R2]

        
        # calculate distance
        # note 10* to get angstroms
        d = 10*np.sqrt(np.square(np.transpose(COM_1)[0] - np.transpose(COM_2)[0]) + np.square(np.transpose(COM_1)[1] - np.transpose(COM_2)[1])+np.square(np.transpose(COM_1)[2] - np.transpose(COM_2)[2]))
        
        # finally fill in the table

        return d
        


    # ........................................................................
    #
    #
    def get_inter_residue_COM_vector(self, R1, R2, correctOffset=True, stride=1):
        """
        Function which calculates the complete set of distances between two residues'
        centers of mass (COM) and returns the inter-residue distance vector. 

        NOTE: This gives a VECTOR and not the distance between the two centers of 
        mass (which is calculated by get_inter_residue_COM_distance)
        

        ........................................
        OPTIONS 
        ........................................
        R1 [int]
        Residue index of first residue

        R2 [int] 
        Residue index of second residue

        correctOffset [Bool] {True}
        Defines if we perform local protein offset correction
        or not. By default we do, but some internal functions
        may have already performed the correction and so don't
        need to perform it again.

        stride [int] {20}     
        Defines the spacing betwen frames to compare with - i.e. take every $stride-th frame.
        Setting stride=1 would mean every frame is used, which would mean you're doing an
        all vs. all comparions, which would be ideal BUT may be slow.



        """

        if correctOffset:
            R1 = self.get_offset_residue(R1)
            R2 = self.get_offset_residue(R2)
        else:
            R1 = int(R1)
            R2 = int(R2)

        TRJ_1 = self.traj.atom_slice(self.topology.select('resid %i' % R1 ))
        TRJ_1 = TRJ_1.slice(list(range(0, self.n_frames, stride)))

        TRJ_2 = self.traj.atom_slice(self.topology.select('resid %i'% R2 ))
        TRJ_2 = TRJ_2.slice(list(range(0, self.n_frames, stride)))
        
        COM_1 = md.compute_center_of_mass(TRJ_1)
        COM_2 = md.compute_center_of_mass(TRJ_2)

        # note 10* to get Angstroms
        return (COM_1 - COM_2)


    # ........................................................................
    #
    #
    def get_inter_residue_atomic_distance(self, R1, R2, A1='CA', A2='CA', mode='atom', correctOffset=True, stride=1):
        """
        Function which returns the distance between two specific atoms on two residues. The atoms
        selected are based on the 'name' field from the topology selection language. This defines
        a specific atom as defined by the PDB file. By default A1 and A2 are CA (C-alpha) but one
        can define any residue of interest. 

        We do not perform any sanity checking on the atom name - this gets really hard - so have an
        explicit try/except block which will warn you that you've probably selected an illegal atom
        name from the residues.

        Distance is returned in Angstroms.

        ........................................
        OPTIONS 
        ........................................
        R1 [int]
        Residue index of first residue

        R2 [int] 
        Residue index of second residue

        A1 [string] {CA}
        Atom name of the atom in R1 we're looking at

        A2 [string {CA}
        Atom name of the atom in R2 we're looking at

        mode [string] {'atom'}
        Mode allows the user to define differnet modes for computing atomic distance. The
        default is 'atom' whereby a pair of atoms (A1 and A2) are provided. Other options
        are detailed below and are identical to those offered by mdtraj in compute_contacts
        
        'ca' - same as setting 'atom' and A1='CA' and A2='CA', this uses the C-alpha atoms
        
        'closest' - closest atom associated with each of the residues, i.e. the is the point
                    of closest approach between the two residues 

        'closest-heavy' - same as closest, except only non-hydrogen atoms are considered

        'sidechain' - closest atom where that atom is in the sidechain. Note this requires
                      mdtraj version 1.8.0 or higher.

        'sidechain-heavy' - closest atom where that atom is in the sidechain and is heavy. 
                            Note this requires mdtraj version 1.8.0 or higher.

        correctOffset [Bool] {True}
        Defines if we perform local protein offset correction
        or not. By default we do, but some internal functions
        may have already performed the correction and so don't
        need to perform it again.

        stride [int] {1}     
        Defines the spacing betwen frames to compare with - i.e. take every $stride-th frame.
        Setting stride=1 would mean every frame is used, which would mean you're doing an
        all vs. all comparions, which would be ideal BUT may be slow.


        """

        # check mode keyword is valid
        ctutils.validate_keyword_option(mode, ['atom', 'ca', 'closest-heavy', 'closest', 'sidechain', 'sidechain-heavy'] , 'mode')
        
        # define R1 and R2 - if offset needed perform, else 
        # define the first and last residue INCLUDING caps
        if correctOffset:
            R1 = self.get_offset_residue(R1)
            R2 = self.get_offset_residue(R2)
        else:
            # cast...
            R1 = int(R1)
            R2 = int(R2)


        try:
            # if atom mode was used
            if mode == 'atom':
                if A1 == 'CA' and A2 == 'CA':

                    subtraj = self.__get_subtrajectory(self.traj, stride)
                    distances = 10*md.compute_contacts(subtraj, [[R1,R2]],scheme='ca')[0].ravel()
                    
                else:
                    atom1 = self.__residue_atom_lookup(R1,A1)
                    if len(atom1) == 0:
                        raise CTException('Unable to find atom [%s] in residue R1 (%i)' % (A1, R1))

                    
                    TRJ_1 = self.traj.atom_slice(atom1)
                    TRJ_1 = self.__get_subtrajectory(TRJ_1, stride)
                    
                    atom2 = self.__residue_atom_lookup(R2,A2)
                    if len(atom2) == 0:
                        raise CTException('Unable to find atom [%s] in residue R1 (%i)' % (A2, R2))

                    TRJ_2 = self.traj.atom_slice(atom2)
                    TRJ_2 = self.__get_subtrajectory(TRJ_2, stride)
                    
                    COM_1 = md.compute_center_of_mass(TRJ_1)
                    COM_2 = md.compute_center_of_mass(TRJ_2)


                    distances = 10*np.sqrt(np.square(np.transpose(COM_1)[0] - np.transpose(COM_2)[0]) + np.square(np.transpose(COM_1)[1] - np.transpose(COM_2)[1])+np.square(np.transpose(COM_1)[2] - np.transpose(COM_2)[2]))
                

        except IndexError as e:
            
            ctio.exception_message("This is likely because one of [%s] or [%s] is not a valid atom type for the residue in question. Full error printed below\n%s" %( A1,A2, str(e)), e, with_frills=True)

        # parse any of the allowed modes in compute_contacts (see http://mdtraj.org/1.8.0/api/generated/mdtraj.compute_contacts.html
        # for more details!)
        if mode == 'closest' or mode == 'ca' or mode == 'closest-heavy' or mode == 'sidechain' or mode == 'sidechain-heavy':
            subtraj = self.__get_subtrajectory(self.traj, stride)
            
            try:
                distances = 10*md.compute_contacts(subtraj, [[R1,R2]], scheme=mode)[0].ravel()
            except ValueError as e:
                raise CTException('Your current version of mdtraj does not support [%s] - please update mdtraj to 1.8.0 or later to facilitate support. Alternatively this may be because residue %i or %i is not parsed correctly by MDTraj. Original error:\n%s' % (mode(), R1, R2, str(e))) 

                        
        # note 10* to get Angstroms
        return distances
        

   
    # ........................................................................
    #
    #
    def get_residue_mass(self, R1, correctOffset=True):
        """
        Returns the mass associated with a specific residue.

        ........................................
        OPTIONS 
        ........................................
        R1 [int]
        Residue index of residue to examine

        correctOffset [Bool] {True}
        Defines if we perform local protein offset correction
        or not. By default we do, but some internal functions
        may have already performed the correction and so don't
        need to perform it again.

        """

        if correctOffset:
            R1 = self.get_offset_residue(R1)
        else:
            R1 = int(R1)
            
        # get the atoms associated with the resite of interest
        res_atoms = self.topology.select('resid %i'%(R1))

        totalMass=0

        for atom in res_atoms:
            totalMass = totalMass + self.topology.atom(atom).element.mass

        return totalMass


    # ........................................................................
    #
    #
    def get_asphericity(self, R1=None, R2=None, correctOffset=True, verbose=True):
        """
        Returns the asphericity associated with the region defined by the intervening stretch of residues between
        R1 and R2. This can be a somewhat slow operation, so a status message is printed for the impatient
        biophysicisit.

        Asphericity is defined in many places - for my personal favourite explanation and definition see
        Page 65 of Andreas Vitalis' thesis (Probing the Early Stages of Polyglutamine Aggregation with 
        Computational Methods, 2009, Washington University in St. Louis).

        ........................................
        OPTIONS 
        ........................................

        R1 [int] {None}
        Index value for first residue in the region of interest. If not 
        provided (False) then first residue is used.

        R1 [int] {None}
        Index value for last residue in the region of interest. If not
        provided (False) then last residue is used.

        correctOffset [Bool] {True}
        Defines if we perform local protein offset correction
        or not. By default we do, but some internal functions
        may have already performed the correction and so don't
        need to perform it again.

        verbose : bool
            Flag that by default is True determines if the function prints status updates. This is relevant because
            this function can be computationally expensive, so having some report on status can be comforting!

        
        """

        # define R1 and R2 - if offset needed perform, else 
        # define the first and last residue INCLUDING caps
        if R1 is None:
            R1 = 0
        else:
            if correctOffset:
                R1 = self.get_offset_residue(R1)
            else:
                # cast...
                R1 = int(R1)

        if R2 is None:
            R2 = self.n_residues - 1
        else:
            if correctOffset:
                R2 = self.get_offset_residue(R2)
            else:
                R2 = int(R2)
        
        # compute the gyration tensor
        gyration_tensor_vector = self.get_gyration_tensor(R1, R2, correctOffset=correctOffset, verbose=verbose)
        asph_vector = []
            
        for gyr in gyration_tensor_vector:

            # calculate the eigenvalues of the gyration tensor!
            (EIG, norm) = LA.eig(gyr)
            
            # finally calculate the instantanous asphericity and append to the growing vector
            asph = 1 - 3*((EIG[0]*EIG[1] + EIG[1]*EIG[2] + EIG[2]*EIG[0])/np.power(EIG[0]+EIG[1]+EIG[2],2))

            asph_vector.append(asph)

        return np.array(asph_vector)
            

    # ........................................................................
    #
    #
    def get_gyration_tensor(self, R1=None, R2=None, correctOffset=True, verbose=True):
        """
        Returns the instantaneous gyration tensor associated with each frame.

        Parameters
        ---------------
        R1 : int  {None}
            Index value for first residue in the region of interest. If not provided (False) then first 
            residue is used.
        

        R1 : int {None}
            Index value for last residue in the region of interest. If not provided (False) then last 
            residue is used.
            

        correctOffset: bool {True}
            Defines if we perform local protein offset correction or not. By default we do, but some 
            internal functions may have already performed the correction and so don't need to perform 
            it again

        verbose : bool
            Flag that by default is True determines if the function prints status updates. This is relevant because
            this function can be computationally expensive, so having some report on status can be comforting!

        Returns
        -----------
        np.ndarray
            Returns a numpy array where each position is the frame-specific gyration tensor value
        
        
        """

        # define R1 and R2 - if offset needed perform, else 
        # define the first and last residue INCLUDING caps
        if R1 is None:
            R1 = 0
        else:
            if correctOffset:
                R1 = self.get_offset_residue(R1)
            else:
                # cast...
                R1 = int(R1)

        if R2 is None:
            R2 = self.n_residues - 1
        else:
            if correctOffset:
                R2 = self.get_offset_residue(R2)
            else:
                R2 = int(R2)

        # switch em around so the A to B syntax makes sense
        if R1 > R2:
            tmp = R2
            R2 = R1
            R1 = tmp        
                            
        all_positions_all_frames = self.traj.atom_slice(self.topology.select('resid %i to %i'%(R1,R2)))

        gyration_tensor_vector = []
        count = 1

        for frame in all_positions_all_frames:

            # quick status update...
            if count % 500 == 0:
                ctio.status_message("On frame %i of %i [computing gyration tensor]" % (count, len(all_positions_all_frames)), verbose)

            count = count + 1
            
            # compute the center of mass for the relevant atoms
            COM = md.compute_center_of_mass(frame)

            # calculate the COM to position difference matrix
            DIF = frame.xyz[0] - COM
        
            # old slow method
            """
            T_PRE = 0.0
            # for each atom in the frame calculate the outer product (dyadic product) of 
            # the difference between the position at the overall center of mass. This creates a 
            # 3x3 gyration tensor
            for pos in frame.xyz[0]:
                T_PRE = T_PRE + np.outer(pos - COM, pos - COM)
             
            T = T_PRE/len(frame.xyz[0])
            """
            
            # compute the gyration tensor - this syntax is WAY faster than the above 
            T_new = np.sum(np.einsum('ij...,i...->ij...',DIF,DIF),axis=0)/len(frame.xyz[0])
            
            gyration_tensor_vector.append(T_new)


        return np.array(gyration_tensor_vector)


    # ........................................................................
    #
    #
    def get_end_to_end_distance(self, mode='COM'):
        """
        Returns the vector assocaiated with the end-to-end distance for the 
        simulation. 

        The vector of End-to-end distances is returned in angstroms

        Parameters
        ---------------
        mode [string] {'CA'}
        String, must be one of either 'CA' or 'COM'.
        'CA' = alpha carbon
        'COM' = center of mass (associated withe the residue) 

        Returns
        ---------
            

        """
        
        ctutils.validate_keyword_option(mode, ['CA', 'COM'], 'mode')

        # extract first and last residue AFTER offset correction (i.e. residue number from original PDB file) 
        start = self.resid_with_CA[0]
        end = self.resid_with_CA[-1]

        if mode == 'CA':
            distance = self.get_inter_residue_atomic_distance(start, end, stride=1, correctOffset=False)
            
        elif mode == 'COM':
            distance = self.get_inter_residue_COM_distance(start, end, stride=1, correctOffset=False)

        return distance
        
                    
    # ........................................................................
    #
    #
    def get_radius_of_gyration(self, R1=None, R2=None, correctOffset=True):
        """
        Returns the radius of gyration associated with the region defined by the intervening stretch of residues between
        R1 and R2. When residues are not provided the full protein's radius of gyration (INCLUDING the caps,
        if present) is calculated.

        Radius of gyration is returned in Angstroms.
        
        Parameters
        ---------------
        R1 : int  {None}
            Index value for first residue in the region of interest. If not 
            provided (None) then first residue is used.

        R2 : int {None}
            Index value for last residue in the region of interest. If not
            provided (False) then last residue is used.

        correctOffset : bool {True}
            Defines if we perform local protein offset correction or not. By default we do, but some internal 
            functions may have already performed the correction and so don't need to perform it again.
        
        Returns
        -----------
        np.ndarray 
            Returns a numpy array with per-frame instantaneous radius of gyration


        """

        # define R1 and R2 - if offset needed perform, else 
        # define the first and last residue INCLUDING caps
        if R1 is None:
            R1 = 0
        else:
            R1 = int(R1)

        if R2 is None:
            R2 = self.n_residues-1
        else:
            R2 = int(R2)


        # note we correct offset regardless of if R1/R2 are passed or not
        if correctOffset:
            R1 = self.get_offset_residue(R1)
            R2 = self.get_offset_residue(R2)

        # switch em around so the A to B syntax makes sense
        if R1 > R2:
            tmp = R2
            R2 = R1
            R1 = tmp

        # in angstroms
        return 10*md.compute_rg(self.traj.atom_slice(self.topology.select('resid %i to %i'%(R1, R2))))


    # ........................................................................
    #
    #
    def get_hydrodynamic_radius(self, R1=None, R2=None, alpha1=0.216, alpha2=4.06, alpha3=0.821, correctOffset=True):
        """
        Returns the apparent hydrodynamic radius as calculated based on the approximation
        derived by Nygaard et al. [1]. Returns a hydrodynamic radius in Angstroms.

        Parameters (alpha1/2/3 should not be altered to recapitulate behaviour defined
        by Nygaard et al.


        References:
        -------------
        [1] Nygaard M, Kragelund BB, Papaleo E, Lindorff-Larsen K. An Efficient 
        Method for Estimating the Hydrodynamic Radius of Disordered Protein 
        Conformations. Biophys J. 2017;113: 550–557.

        Radius of gyration is returned in Angstroms.


        Parameters
        ---------------
        R1 : int {False}
            Index value for first residue in the region of interest. If not 
            provided (False) then first residue is used.

        R2 : int {False}
            Index value for last residue in the region of interest. If not
            provided (False) then last residue is used.

        alpha1 : float {0.216}
           First parameter in equation (7) from Nygaard et al.

        alpha2 : float {4.06}
           Second parameter in equation (7) from Nygaard et al.

        alpha3 : float {0.821}
           Third parameter in equation (7) from Nygaard et al.
        
        correctOffset : bool {True}
            Defines if we perform local protein offset correction or not. By default we do, 
            but some internal functions may have already performed the correction and so don't
            need to perform it again.

        Returns
        -----------
        np.ndarray 
            Returns a numpy array with per-frame instantaneous hydrodynamic radii


        """

        # first compute the rg
        rg = self.get_radius_of_gyration(R1, R2, correctOffset)

        # precompute
        N_033 = np.power(self.n_residues, 0.33)
        N_060 = np.power(self.n_residues, 0.60)
        
        Rg_over_Rh = ((alpha1*(rg - alpha2*N_033)) / (N_060 - N_033)) + alpha3

        return (1/Rg_over_Rh)*rg


    # ........................................................................
    #
    #
    def get_t(self, R1=None, R2=None, correctOffset=True):
        """
        Returns the <t>, a dimensionless parameter which describes the 
        size of the ensemble. 


        Parameters
        ---------------
        R1 : int {None}
            Index value for first residue in the region of interest. If not 
            provided (False) then first residue is used.

        R2 : int {None}
            Index value for last residue in the region of interest. If not
            provided (False) then last residue is used.

        correctOffset : bool {True}
            Defines if we perform local protein offset correction or not. By 
            default we do, but some internal functions may have already performed 
            the correction and so don't need to perform it again.

        Returns
        -----------
        np.ndarray 
            Returns a numpy array with per-frame instantaneous t-values

        """

        # define R1 and R2 - if offset needed perform, else 
        # define the first and last residue INCLUDING caps
        if R1 is None:
            R1 = 0
        else:
            R1 = int(R1)

        if R2 is None:
            R2 = self.n_residues-1
        else:
            R2 = int(R2)
        
        # first get the instantanoues RG
        rg = self.get_radius_of_gyration(R1, R2, correctOffset)
        n_res = self.n_residues
        c_length = n_res * 3.6

        # next define the exponent 
        exponent = 4.0/(np.power(n_res,0.3333))
        
        # define a function which returns the instantaneous t value for
        # a given rg
        def inst_t(i):
            return 2.5*np.power((1.75*(i/(c_length))),exponent)
        
        # compile into a vectorized version
        K = np.vectorize(inst_t)

        # run over all rg
        return K(rg)
        
        

    # ........................................................................
    #
    #    
    def get_internal_scaling(self, R1=None, R2=None, mode='COM', mean_vals=False, correctOffset=True, stride=1, weights=False, verbose=True):
        """
        Calculates the raw internal scaling info for the protein in the simulation.
        R1 and R2 define a sub-region to operate over if sub-regional analysis is
        required. When residues are not provided the full protein's internal scaling 
        (EXCLUDING* the caps, if present) is calculated.       

        Distance is measured in Angstroms.

        Returns two lists of the same length

        1) List of arrays, where each array is the simulation average set of inter-residue 
           distances for the primary sequence separation defined by the equivalent position
           in the second array. Each array in this list will be a different length as there
           are many more i to i+1 pairs of residues than i to i+10 (e.g. in a 15 residue 
           sequence).

        2) The sequence separation associated with each set of measurements (i.e. a single
           list which will normally be 0,1,2,3,...n where n = number of residues in sequence.

        The internal scaling profile is a plot of sequence separation vs. mean through-space distance for 
        all pairs of residues at a given sequence separation. What this means is that if we had a 6 residue
        peptide the internal scaling profile would be calculated as follows.                        

        sequence separation = 0
        average distance(average distance of 1-to-1, 2-to-2, 3-to-3, etc.)

        sequence separation = 1
        average distance(average distance of 1-to-2, 2-to-3, 3-to-4, etc.)

        sequence separation = 2
        average distance(average distance of 1-to-3, 2-to-4, 3-to-5, etc.)

        sequence separation = 3
        average distance(average distance of 1-to-4, 2-to-5, 3-to-6.)

        sequence separation = 4
        average distance(average distance of 1-to-5, 2-to-6)

        sequence separation = 5
        average distance(average distance of 1-to-6)
        

        The residues considered for internal scaling analysis DO NOT include the ACE/NME 
        peptide caps if present. This differs from CAMPARI, which DOES include the peptide
        caps.

        For more information on this and other ideas for how polymer-physics can be a useful 
        way of thinking about proteins, take a look at        

        Mao, A.H., Lyle, N., and Pappu, R.V. (2013). Describing sequence-ensemble relationships for 
        intrinsically disordered proteins. Biochem. J 449, 307-318.

        and 

        Pappu, R.V., Wang, X., Vitalis, A., and Crick, S.L. (2008). A polymer physics perspective on 
        driving forces and mechanisms for protein aggregation - Highlight Issue: Protein Folding. 
        Arch. Biochem. Biophys. 469, 132-141.

        * The exclusion of the caps is different to how this is calculated in CAMPARI, 
        which includes the caps, if present.

        ........................................
        OPTIONS 
        ........................................

        R1 [int] {False}
        Index value for first residue in the region of interest. If not 
        provided (False) then first residue is used.

        R1 [int] {False}
        Index value for last residue in the region of interest. If not
        provided (False) then last residue is used.

        mode ['CA' or 'COM'] {'CA'}
        Defines the mode used to define the residue position, either the
        residue center or mass or the residue CA atom. The provided mode
        must be one of these two options.

        mean_vals [Book] {False}
        This is False by default, but if true the mean IS is returned instead of 
        the explicit values. In reality the non-default behaviour is probably
        preferable...

        correctOffset [Bool] {True}
        Defines if we perform local protein offset correction
        or not. By default we do, but some internal functions
        may have already performed the correction and so don't
        need to perform it again.

        stride : int {1}
            Defines the spacing between frames to compare - i.e. if comparing frame1 to a trajectory 
            we'd compare frame 1 and every stride-th frame. Note this operation may scale poorly as 
            protein length increases at which point increasing the stride may become necessary.


        weights [list or array of floats] {False}
        Defines the frame-specific weights if re-weighted analysis is required. This can be 
        useful if an ensemble has been re-weighted to better match experimental data, or in
        the case of analysing replica exchange data that is re-combined using T-WHAM.

        verbose : bool
            Flag that by default is True determines if the function prints status updates. This is relevant because
            this function can be computationally expensive, so having some report on status can be comforting!

        
        """

        if weights is not False:
            if int(stride) != 1:
                raise CTException("For get_scaling_exponent with weights stride MUST be set to 1. If this is a HUGE deal for you please contact alex and he'll try and update the code to accomodate this, but for now we suggest creating a sub-sampled trajectory and loading that")

        # check weights are correct
        weights = self.__check_weights(weights, stride)

        # check stride is ok
        self.__check_stride(stride)

        # check mode is OK
        ctutils.validate_keyword_option(mode, ['CA', 'COM'], 'mode')

        # process the R1/R2 to set the position after offset correction
        out =  self.__get_first_and_last(R1, R2, withCA = True)
        R1 = out[0]
        R2 = out[1]

        # check the R1/R2 positions contina a CA (not R1 and R2 here are after
        # offset has been applied. This throws an exception if no CA
        self.__check_contains_CA(R1)
        self.__check_contains_CA(R2)
        
        max_seq_sep = (R2 - R1) + 1

        # if chain is too short...
        if max_seq_sep < 1:
            return ([], [])

        seq_sep_distances = []
        seq_sep_vals = []

        for seq_sep in range(0, max_seq_sep):
            ctio.status_message("Internal Scaling - on sequence separation %i of %i" %(seq_sep, max_seq_sep-1), verbose)

            tmp = []
            seq_sep_vals.append(seq_sep)
            for pos in range(0, max_seq_sep-seq_sep):

                # define the two positions
                A = R1 + pos
                B = R1 + pos+seq_sep
                
                # get the distance for every stride-th frame between those two positions using either the CA
                # mode or the COM mode
                if mode == 'CA':
                    distance = self.get_inter_residue_atomic_distance(A, B, stride=stride, correctOffset=False)

                elif mode == 'COM':
                    distance = self.get_inter_residue_COM_distance(A, B, stride=stride, correctOffset=False)

                # if weights were provided subsample from the set of distances using the weights vector
                if weights is not False:
                    distance = choice(distance, len(distance), p=weights)

                tmp = np.concatenate((tmp,distance))
                
            seq_sep_distances.append(tmp)

        if mean_vals:
            mean_is = [np.mean(i) for i in seq_sep_distances]
            return (seq_sep_vals, mean_is)
        else:
            return (seq_sep_vals, seq_sep_distances)



    # ........................................................................
    #
    #    
    def get_internal_scaling_RMS(self, R1=None, R2=None, mode='COM', stride=1, correctOffset=True, weights=False, verbose=True):
        """
        If :math:`r_{i,j} = \langle \langle \sum \sigma_{1}` equals :math:`\sigma_{2}` then etc, etc.


        Calculates the averaged internal scaling info for the protein in the simulation in terms of
        root mean square (i.e. `sqrt(<Rij^2>`) vs `| i - j |`.

        R1 and R2 define a sub-region to operate over if sub-regional analysis is
        required. When residues are not provided the full protein's internal scaling 
        (EXCLUDING* the caps, if present) is calculated.       

        Distance is measured in Angstroms.

        Returns two lists of the same length:

        1) sequence separation (`|i - j|`)

        2) mean sqrt(`<Rij^2>`) 
        
        The internal scaling profile is a plot of sequence separation vs. mean through-space distance for 
        all pairs of residues at a given sequence separation. What this means is that if we had a 6 residue
        peptide the internal scaling profile would be calculated as follows.                        

        sequence separation = 0
        average distance(average distance of 1-to-1, 2-to-2, 3-to-3, etc.)

        sequence separation = 1
        average distance(average distance of 1-to-2, 2-to-3, 3-to-4, etc.)

        sequence separation = 2
        average distance(average distance of 1-to-3, 2-to-4, 3-to-5, etc.)

        sequence separation = 3
        average distance(average distance of 1-to-4, 2-to-5, 3-to-6.)

        sequence separation = 4
        average distance(average distance of 1-to-5, 2-to-6)

        sequence separation = 5
        average distance(average distance of 1-to-6)
        

        The residues considered for internal scaling analysis DO NOT include the ACE/NME 
        peptide caps if present. This differs from CAMPARI, which DOES include the peptide
        caps.

        For more information on this and other ideas for how polymer-physics can be a useful 
        way of thinking about proteins, take a look at        

        Mao, A.H., Lyle, N., and Pappu, R.V. (2013). Describing sequence-ensemble relationships for 
        intrinsically disordered proteins. Biochem. J 449, 307-318.

        and 

        Pappu, R.V., Wang, X., Vitalis, A., and Crick, S.L. (2008). A polymer physics perspective on 
        driving forces and mechanisms for protein aggregation - Highlight Issue: Protein Folding. 
        Arch. Biochem. Biophys. 469, 132-141.

        * The exclusion of the caps is different to CAMPARI, which includes the caps, if present.

        ........................................
        OPTIONS 
        ........................................

        R1 [int] {None}
        Index value for first residue in the region of interest. If not 
        provided (False) then first residue is used.

        R1 [int] {None}
        Index value for last residue in the region of interest. If not
        provided (False) then last residue is used.

        mode ['CA' or 'COM'] {'CA'}
        Defines the mode used to define the residue position, either the
        residue center or mass or the residue CA atom. The provided mode
        must be one of these two options.

        correctOffset [Bool] {True}
        Defines if we perform local protein offset correction
        or not. By default we do, but some internal functions
        may have already performed the correction and so don't
        need to perform it again.

        weights [list or array of floats] {False}
        Defines the frame-specific weights if re-weighted analysis is required. This can be 
        useful if an ensemble has been re-weighted to better match experimental data, or in
        the case of analysing replica exchange data that is re-combined using T-WHAM.

        verbose : bool
            Flag that by default is True determines if the function prints status updates. This is relevant because
            this function can be computationally expensive, so having some report on status can be comforting!
        
        """
        
        # compute the non RMS internal scaling behaviour 
        (seq_sep_vals, seq_sep_distances) = self.get_internal_scaling(R1=R1, R2=R2, mode=mode, stride=stride, correctOffset=correctOffset, weights=weights, verbose=verbose)
        
        # calculate RMS for each distance 
        mean_is = [np.sqrt(np.mean(i*i)) for i in seq_sep_distances]

        return (seq_sep_vals, mean_is)


    # ........................................................................
    #
    def get_scaling_exponent(self, inter_residue_min=15, end_effect=5, correctOffset=True,  subdivision_batch_size=20, mode='COM', num_fitting_points=40, fraction_of_points=0.5, fraction_override=False, stride=1, weights=False, verbose=True):
        """
        Estimation for the A0 and nu exponents for the standard polymer relationship

        sqrt(<Rij^2>) = A0|i-j|^(nu)

        Nu reports on the solvent quality, while the prefactor (A0) reports on the average chain persistence length. For polymers that are
        above a 0.5 scaling exponent this works, but below this they deviate from fractal behaviour, so formally this relationship stops 
        working. In practice, the best possible fit line does still track with relative compactness.

        Returns a 9 position tuple with the following associated values:
        0 - best nu

        1 - best A0

        2 - minimum nu identified in bootstrap fitting

        3 - maximum nu identified in bootstrap fitting

        4 - minimum A0 identified in bootstrap fitting

        5 - maximum A0 identified in bootstrap fitting

        6 - reduced chi^2 for the fit region

        7 - reduced chi^2 for ALL points

        8 - 2-column array, where col 1 is the sequence separation and col 2
            is the real spatila separation for the ACTUAL data used to fit to
            the polymer model (i.e. these points are uniformly spaced from 
            one another on a log-log plot). Reduced chi^2 for the fit region
            is calculated using this dataset. 

        9 - 3-column array, where col 1 is the sequence separation, col 2 is 
            the real spatial separation observed and col 3 is the best fit 
            curve, for ALL i-j distances. Reduced chi^2 for all points is
            calculated using this dataset.

        NOTE: Despite their precision nu and A0 should be treated as qualitative metrics, and are subject to finite
              chain effects. The idea of a polymer scaling behaviour is only necessarily useful in the case of a 
              homopolymer, whereas heterpolymers engender massive averaging that can mask underlying conformational
              complexity. We _strongly_ caution against over interpretation of the scaling exponent. For a better
              assement of how your chain actually deviates from homopolymer behaviour, see the function
              get_polymer_scaled_distance_map()

        ........................................
        OPTIONS 
        ........................................
        inter_residue_min [int] {15}
        Minimum distances used when selecting pairs of residues. This 25 threshold was determined previously,
        and essentially avoids scenarios where the two residues (i and j) are close to each other. The goal 
        of this limit is to avoid finite chain size strongly influencing the scaling exponent limit.

        end_effect [int] {5}
        Avoid pairs where one of the residues is $end_effect residues from the end. Helps mitigate end-effects.
        5 chosen as it's around above the blob-length in a polypeptide. Note that for homopolymers this is much 
        less of an issue.

        correctOffset [Bool] {True}
        Defines if we perform local protein offset correction
        or not. By default we do, but some internal functions
        may have already performed the correction and so don't
        need to perform it again.

        mode [string, either 'COM' or 'CA'] {'COM'}
        Defines the mode in which the internal scaling profile is calculated, can use either
        COM (center of mass) of each residue or the CA carbon of each residue. COM is more
        appropriate as CA will inherently give a larger profile.

        num_fitting_points [int] {40}
        Number of evenly spaced points to used to fit the scaling exponent in loglog space. 40 
        seems to be a decent number that scales well

        fraction_of_points [float between 0 and 1] {0.5}
        This is only used if fraction_override is set to True OR the sequence has less than 
        the num_of_fitting_points residues. Means that instead of using a an absolute number
        of points (e.g. 40) to fit the loglog data, we use this fraction of residues. i.e.
        if the protein had 20 residues and fraction_of_points = 0.5 we'd use 10 points

        fraction_override [bool] {False}
        If set to False then fraction_of_points ONLY used if the length of the sequence is
        less than the num_fitting points. If true then we explicitly use fraction_of_points
        and ignore num_fitting_points.

        stride : int {1}
            Defines the spacing between frames to compare - i.e. if comparing frame1 to a trajectory 
            we'd compare frame 1 and every stride-th frame. Note this operation may scale poorly as 
            protein length increases at which point increasing the stride may become necessary.


        weights [list or array of floats] {False}
        Defines the frame-specific weights if re-weighted analysis is required. This can be 
        useful if an ensemble has been re-weighted to better match experimental data, or in
        the case of analysing replica exchange data that is re-combined using T-WHAM.

        verbose : bool
            Flag that by default is True determines if the function prints status updates. This is relevant because
            this function can be computationally expensive, so having some report on status can be comforting!



        
        """
        
        # check weights are OK
        weights = self.__check_weights(weights, stride)

        # check mode is OK
        ctutils.validate_keyword_option(mode, ['CA', 'COM'], 'mode')

        # compute max |i-j| distance being used...
        first = self.resid_with_CA[0]
        last= self.resid_with_CA[-1]
        max_separation = (last-first)+1

        #  if we're not using fraction override check the number of points requested makes sense given sequence length
        if not fraction_override and (max_separation - (end_effect+inter_residue_min)) < num_fitting_points:
            fraction_of_points=1.0
            ctio.warning_message("For scaling exponent calculation, sequence not long enough to use %i points (only %i valid positions once end effects and low |i-j| are accounted for), switching to using the fraction of points mode (will use %i points instead)" % (num_fitting_points, (max_separation - (end_effect+inter_residue_min)), int(fraction_of_points*(max_separation - (end_effect+inter_residue_min)))))
            
            fraction_override = True
            
        if fraction_override:
            if fraction_of_points > 1.0:
                raise CTException("Using fraction_overide to define the number of points to fit in the linear loglog analysis, but requested over 1.0 fraction (fraction_of_points must lie between >=0 and 1.0")
            # again note int to round down here
            num_fitting_points = int(fraction_of_points*(max_separation - (end_effect+inter_residue_min)))
            if num_fitting_points < 3:
                raise CTException("Less than three points - cannot fit a straight line")
            if num_fitting_points < 10:
                ctio.warning_message("Warning: Scaling fit has only %i points - likely finite size effects!" % (num_fitting_points))


        # check weights make sense...
        weights = self.__check_weights(weights, stride)

        # check that the number of points being used makes sense..        

        # This section determines the number of subdivisions performed for error 
        # bootstrapping. If we have fewer frames than we can divide the data into
        # then we just use each frame individually (although now error bootstrapping
        # is probably meaningless!
        # note integer math used here to round down - also set 
        if int(self.n_frames/stride) < int(subdivision_batch_size):        
            num_subdivisions_for_error = int(self.n_frames/stride)
        else:
            num_subdivisions_for_error = int(int(self.n_frames/stride) / subdivision_batch_size)
                
        seq_sep_vals             = []
        seq_sep_RMS_distance     = []
        seq_sep_RMS_var_distance     = []
        seq_sep_RSTDS_distance   = []
        seq_sep_subsampled_distances  = []
        
        # for each possible sequence separation  (|i-j| value)
        for seq_sep in range(1, max_separation):

            ctio.status_message("Internal Scaling - on sequence separation %i of %i" %(seq_sep, max_separation), verbose)

            tmp = []
            seq_sep_vals.append(seq_sep)

            # collect all possible average seq-sep values weighted by the weights
            for pos in range(0, max_separation-seq_sep):

                # define the two positions
                A = first + pos
                B = first + pos + seq_sep


                if mode == 'CA':
                    distance = self.get_inter_residue_atomic_distance(A, B, stride=stride, correctOffset=False)

                elif mode == 'COM':
                    distance = self.get_inter_residue_COM_distance(A, B, stride=stride, correctOffset=False)

                # compute the ensemble average of the distances
                if weights is not False:
                    distance = choice(distance, len(distance), p=weights)

                tmp.extend(distance)
            
            tmp = np.array(tmp)
            
            # add mean and std vals for this sequence sep            
            seq_sep_RMS_distance.append(np.sqrt(np.mean(tmp*tmp)))
            seq_sep_RSTDS_distance.append(np.sqrt(np.std(tmp*tmp)))
            seq_sep_RMS_var_distance.append(np.sqrt(np.power(np.var(tmp),2)))

            if num_subdivisions_for_error > 0:

                # note we cast this to an int to ensure subdivision_size is always
                # the value added to RMS_local_append is always the same, because
                # len(tmp) will vary with sequence separation. Basically this means
                # we take ALL the data and subidivided it into num_subdivisions_for_error
                # chunks and then use this for error calculations
                subdivision_size = int(len(tmp)/num_subdivisions_for_error)

                # get shuffled indices
                idx = np.random.permutation(list(range(0,len(tmp))))
            
                # split shuffled indices into $num_subdivisions_for_error sized chunks
                
                subdivided_idx = cttools.chunks(idx, subdivision_size)
                        
                # finally subselect each of the randomly selected indicies 
                RMS_local   = []
            
                for idx_set in subdivided_idx:
                    
                    # subselect a random set of distances and compute RMS
                    RMS_local.append(np.sqrt(np.mean(tmp[idx_set]*tmp[idx_set])))
            
                # add distribution of values for this sequence sep
                seq_sep_subsampled_distances.append(RMS_local)

        # now sub-select the bit of the curve we actually want for the separation, distance, and distance variance data
        # note we are RE DEFINING these three variables here
        seq_sep_vals = seq_sep_vals[inter_residue_min:-end_effect]
        seq_sep_RMS_distance = seq_sep_RMS_distance[inter_residue_min:-end_effect]
        seq_sep_RMS_var_distance = seq_sep_RMS_var_distance[inter_residue_min:-end_effect]
                
        ## next find indices for evenly spaced points in logspace. This whole sectino
        # leads to the identification of the indices in logspaced_idx, which are the
        # list indices that will given evenly spaced points when plotted in log space 
        y_data = np.log(seq_sep_vals)
        y_data_offset = y_data - y_data[0]
        interval = y_data_offset[-1]/num_fitting_points
        integer_vals = y_data_offset/interval
        
        logspaced_idx = []
        for i in range(0,num_fitting_points):
            [local_ix,_] = cttools.find_nearest(integer_vals, i) 
            if local_ix in logspaced_idx:
                continue
            else:
                logspaced_idx.append(local_ix)

        # finally using those evenly-spaced log indices we extract out new lists
        # that have values which will be evenly spaced in logspace. Cool.
        fitting_separation = [seq_sep_vals[i] for i in logspaced_idx]
        fitting_distances  = [seq_sep_RMS_distance[i] for i in logspaced_idx]
        fitting_variance   = [seq_sep_RMS_var_distance[i] for i in logspaced_idx]

        # fit to a log/log model and extract params
        out = np.polyfit(np.log(fitting_separation), np.log(fitting_distances), 1)
        nu_best = out[0]
        R0_best = np.exp(out[1])

        ## >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
        ### next calculated reduced chi-squared
        n_points = len(fitting_distances)
        chi2=0
        for i in range(0, n_points):
            chi2 = chi2 + (np.power(np.log(fitting_distances[i]) - nu_best*np.log(fitting_separation[i])+R0_best,2))/fitting_variance[i]

        # finally calculated reduced chi squared correcting for 2 model parameters
        reduced_chi_squared_fitting = chi2 / (n_points-2)


        full_n_points = len(seq_sep_vals)

        chi2=0
        for i in range(0, full_n_points):
            chi2 = chi2 + (np.power(np.log(seq_sep_RMS_distance[i]) - nu_best*np.log(seq_sep_vals[i])+R0_best,2))/seq_sep_RMS_var_distance[i]

        # finally calculated reduced chi squared correcting for 2 model parameters
        reduced_chi_squared_all = chi2 / (full_n_points-2)


            
        ## >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
        ### Finally run the subselection protocol to subsampled

        subselected = np.array(seq_sep_subsampled_distances).transpose()
        
        nu_sub = []
        R0_sub = []
        for i in range(0, num_subdivisions_for_error):
             
            local_distances = subselected[i][inter_residue_min:-end_effect]
 
            OF = np.polyfit(np.log(fitting_separation), np.log([local_distances[i] for i in logspaced_idx]), 1)
 
            nu_sub.append(OF[0])
            R0_sub.append(np.exp(OF[1]))
 
        if num_subdivisions_for_error < 1:
            nu_sub.append(np.nan)
            R0_sub.append(np.nan)


        return [nu_best, R0_best, min(nu_sub), max(nu_sub), min(R0_sub), max(R0_sub),  reduced_chi_squared_fitting, reduced_chi_squared_all, np.vstack((np.array(fitting_separation),np.array(fitting_distances))), np.vstack((seq_sep_vals, seq_sep_RMS_distance, cttools.powermodel(seq_sep_vals, nu_best, R0_best)))]




    # ........................................................................
    #
    #
    def get_residue_COM(self, R1, correctOffset=True):
        """
        Returns the COM vector for the residue across the trajectory.

        ........................................
        OPTIONS 
        ........................................
        
        R1 [int] 
        Index value for the residue of interest

        correctOffset [Bool] {True}
        Defines if we perform local protein offset correction
        or not. By default we do, but some internal functions
        may have already performed the correction and so don't
        need to perform it again.

     
        """

        # correct the offset if necessary
        if correctOffset:
            R1 = self.get_offset_residue(R1)
        else:
            R1 = int(R1)
        
        # get the atoms associated with the resite of interest
        return md.compute_center_of_mass(self.traj.atom_slice(self.topology.select('resid %i'%R1)))



    # ........................................................................
    #
    #
    def get_all_SASA(self, probe_radius=0.14, mode='residue', stride=20):
        """
        Returns the Solvent Accessible Surface Area (SASA) for each residue from 
        every stride-th frame. SASA is determined using shrake_rupley algorithm.

        SASA is returned in Angstroms squared, BUT PROBE RADIUS is in nanometers!
                       
        ........................................
        OPTIONS 
        ........................................
        
                
        probe_radius [float]  {0.14}
        Radius of the solvent probe used in nm. Uses the Golden-Spiral algorithm. 
        0.14 nm is pretty standard. NOTE - the probe radius must be in nanometers

        mode [string] {'residue','atom','sidechain','backbone', 'all'}
        Defines the mode used to compute the SASA. Must be one of 'residue' or 
        'atom'. For atom mode, extracted areas are resolved per-atom. For 'residue',
        this is computed instead on the per residue basis. 

        stride [int] {20}
        Defines the spacing between frames to compare - i.e. if comparing frame1 
        to a trajectory we'd compare frame 1 and every stride-th frame
        
        
        """
        
        ## >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
        ## internal function
        def get_sasa_based_on_type(basis, passed_mode):
            # get all reas
            all_areas = basis[0]*100
            all_atoms = list(basis[1])

            # note these CA resids are after offset correction has been applied. NOTE we need to
            # check if the atom selection here works for multichain protein systems
            # TODO
            CA_res = self.resid_with_CA
            
            # for each residue with a CA atom...
            residue_SASA=[]
            for i in CA_res:
                
                # get the atomic indices 
                if passed_mode == 'sidechain':
                    # for some reason 'sidechain' selection includes the backbone hydrogen atoms??!?!
                    relevant_atom_idx = self.topology.select('resid %i and %s and (not name H HA HA2 HA3)' % (i,passed_mode)) 
                    

                if passed_mode == 'backbone':
                    # for some reason 'backbone' ignores the backbone hydrogen atoms ?!?!?
                    relevant_atom_idx = self.topology.select('(resid %i and %s) or (resid %i and name H HA HA2 HA3)' % (i,passed_mode, i)) 

                # no atoms so create an empty list
                if len(relevant_atom_idx) == 0:
                    per_res = list(np.zeros(len(all_areas.transpose()[0])))
                else:
                
                    # get SASA index of first atom index...
                    per_res = all_areas.transpose()[all_atoms.index(relevant_atom_idx[0])]

                    for atom in relevant_atom_idx[1:]:
                        per_res = per_res + all_areas.transpose()[all_atoms.index(atom)]

                residue_SASA.append(per_res)

            return np.array(residue_SASA).transpose()
            ## >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>


        # validate input mode
        ctutils.validate_keyword_option(mode, ['residue', 'atom','backbone','sidechain','all'], 'mode')

        # downsample based on the stride        
        target = self.__get_subtrajectory(self.traj, stride)

        # 100* to convert from nm^2 to A^2
        if mode == 'residue':
            return 100*md.shrake_rupley(target, mode='residue', probe_radius=probe_radius)

        if mode == 'atom':
            return 100*md.shrake_rupley(target, mode='atom', probe_radius=probe_radius)
            
        if mode == 'sidechain' or mode == 'backbone' or mode == 'all':
            
            print("WARNING: Not tested on multiprotein systems")

            # run calc
            basis =  md.shrake_rupley(target, mode='atom', probe_radius=probe_radius, get_mapping=True)

            # extract sidechains
            if mode == 'sidechain' or mode == 'all':
                SC_SASA = get_sasa_based_on_type(basis, 'sidechain')

            # extract backbone
            if mode == 'backbone' or mode == 'all':
                BB_SASA = get_sasa_based_on_type(basis, 'backbone')

            if mode == 'all':
                ALL_SASA = 100*md.shrake_rupley(target, mode='residue', probe_radius=probe_radius)
                
            if mode == 'sidechain':
                return SC_SASA

            if mode == 'backbone':
                return SC_SASA

            if mode == 'all':
                return (ALL_SASA, SC_SASA, BB_SASA)
                


    # ........................................................................
    #
    #
    def get_site_accessibility(self, input_list, probe_radius=0.14, mode='residue_type', stride=20):
        """
        Function to compute site/residue type accessibility. This can be done using one of two modes.
        Under 'residue_type' mode, the input_list should be a list of canonical 3-letter amino acid
        names. Under 'resid' mode, the input list should be a list of residue id positions (recall
        that resid ALWAYS starts from 0 and will include the ACE cap if present).

        Returns a dictionary with the key = residue "type-number" string and the value equal
        the average and standard devaition associated with the SASA. Useful for looking at
        comparative accessibility of the same residue accross the sequence.

        ........................................
        OPTIONS 
        ........................................

        input_list [list] 
        List of either residue names (e.g. ['TRP','TYR','GLN'] or resid values
        ([1,2,3,4]) which will be taken and the SASA calculated for.
                        
        probe_radius [float]  {0.14}
        Radius of the solvent probe used in nm. Uses the Golden-Spiral algorithm. 
        0.14 nm is pretty standard. NOTE - the probe radius must be in nanometers

        mode [string] {'residue_type'}
        Mode used to examine sites. MUST be one of 'residue_type' or 'resid'

        stride [int] {20}
        Defines the spacing between frames to compare - i.e. if comparing frame1 
        to a trajectory we'd compare frame 1 and every stride-th frame

               
        
        """

        ## First check mode is valid and then sanity check input
        ctutils.validate_keyword_option(mode, ['residue_type', 'resid'], 'mode')

        # if we're in 'residue_type' mode
        if mode == 'residue_type':

            # set the list of valid residues to the 20 AAs + the caps            
            for res in input_list:
                if res not in ALL_VALID_RESIDUE_NAMES:
                    raise CTException("Error: Tried to use get_site_accessibility in 'residue_type' mode but residue %s not found in list of valid residues %s" % (res, str(ALL_VALID_RESIDUE_NAMES)))

        # if we're in resid mode
        elif mode.lower() == 'resid':
            
            offset_input_idx=[]

            for res in input_list:
                R1 = int(res)

                # check residue makes sense and then calculate the offset
                self.__check_single_residue(R1)
                offset_input_idx.append(self.get_offset_residue(R1))

            

        ## if we get here all input has been validated
        if mode == 'residue_type':

            # get AA list and convert into an ordered list of each 
            # AA residue type
            SEQS = self.get_amino_acid_sequence(numbered=False)

            # initialze the empty idx v
            offset_input_idx = []
            idx=0
            for res in SEQS:
                if res in input_list:
                    offset_input_idx.append(idx)

                idx=idx+1

        
        # next compute ALL SASA for all residues (need the full protein based SASA        
        ALL_SASA = np.transpose(self.get_all_SASA(stride=stride, probe_radius=probe_radius))

        lookup = self.get_amino_acid_sequence()

        return_data={}
        for i in offset_input_idx:
            return_data[lookup[i]] = [np.mean(ALL_SASA[i]), np.std(ALL_SASA[i])]
            
        return return_data
        
    # ........................................................................
    #
    #
    def get_regional_SASA(self, R1, R2, probe_radius=0.14, correctOffset=True, stride=20):
        """
        Returns the Solvent Accessible Surface Area (SASA) for a local region in
        every stride-th frame. SASA is determined using shrake_rupley algorithm.

        SASA is returned in Angstroms squared, BUT PROBE RADIUS is in nanometers!
                       
        ........................................
        OPTIONS 
        ........................................

        R1 [int] 
        Index value for the first residue in the region

        R2 [int]
        Index value for the last residue in the region
                        
        probe_radius [float]  {0.14}
        Radius of the solvent probe used in nm. Uses the Golden-Spiral algorithm. 
        0.14 nm is pretty standard. NOTE - the probe radius must be in nanometers

        correctOffset [Bool] {True}
        Defines if we perform local protein offset correction
        or not. By default we do, but some internal functions
        may have already performed the correction and so don't
        need to perform it again.

        stride [int] {20}
        Defines the spacing between frames to compare - i.e. if comparing frame1 
        to a trajectory we'd compare frame 1 and every stride-th frame
        
                      
        """

        if correctOffset:
            R1 = self.get_offset_residue(R1)
            R2 = self.get_offset_residue(R2)

        # NOTE - we HAVE to compute SASA over the full ensemble to take into acount
        # atoms OUTSIDE the region getting in the way of the regional SASA
        total = self.get_all_SASA(stride=stride, probe_radius=probe_radius)

        total = np.transpose(total)

        regional_SASA = 0 
        for i in range(R1, R2):
            regional_SASA = regional_SASA + np.mean(total[i])
            
        # return the mean sum of SASA for all atoms
        return regional_SASA


    # ........................................................................
    #
    #
    def get_sidechain_alignment_angle(self, R1, R2, sidechain_atom_1='default', sidechain_atom_2='default', correctOffset=True):
        """
        Function that computes the angle alignment between two residue sidechains. Sidechain vectors are defined as the unit vector between the
        CA of the residue and a designated 'sidechain' atom on the sidechain. The default sidechain atoms are listed below, but custom atom
        names can also be provided using the sidechain_atom_1/2 variables. 

        """


        # The initial section is responsible for selecting/defining the sidechain atom and catching any
        # bad inputs. It's a litte drawn out but useful for code clarity reasons.
        # note need to do this with the un-corrected residue index values, hence why it comes first


        if sidechain_atom_1 == 'default':
            resname_1 = self.get_amino_acid_sequence(numbered=False)[R1]                        
            resname_1 = cttools.fix_histadine_name(resname_1)

            try:
                sidechain_atom_1 = DEFAULT_SIDECHAIN_VECTOR_ATOMS[resname_1]

                if sidechain_atom_1 == 'ERROR':
                    raise CTException('Residue lacks a valid sidechain (%s)' % resname_1)

            except KeyError:
                raise CTException('Cannot parse residue at position %i (residue name = %s) ' % (R1, resname_1))

        if sidechain_atom_2 == 'default':
            resname_2 = self.get_amino_acid_sequence(numbered=False)[R2]                        
            resname_2 = cttools.fix_histadine_name(resname_2)

            try:
                sidechain_atom_2 = DEFAULT_SIDECHAIN_VECTOR_ATOMS[resname_2]

                if sidechain_atom_2 == 'ERROR':
                    raise CTException('Residue lacks a valid sidechain (%s)' % resname_2)

            except KeyError:
                raise CTException('Cannot parse residue at position %i (residue name = %s) ' % (R2, resname_2))

        ### At this point we have reasonable atom names defined!

        # 
        if correctOffset:
            R1 = self.get_offset_residue(R1)
            R2 = self.get_offset_residue(R2)

        

        TRJ_1_SC = self.traj.atom_slice(self.topology.select('resid %i and name %s' % (R1, sidechain_atom_1) ))
        TRJ_1_CA = self.traj.atom_slice(self.topology.select('resid %i and name CA' % (R1) ))

        TRJ_2_SC = self.traj.atom_slice(self.topology.select('resid %i and name %s' % (R2, sidechain_atom_2) ))
        TRJ_2_CA = self.traj.atom_slice(self.topology.select('resid %i and name CA' % (R2) ))


        # compute CA-SC vector 
        R1_vector = TRJ_1_SC.xyz - TRJ_1_CA.xyz
        R2_vector = TRJ_2_SC.xyz - TRJ_2_CA.xyz

        # finally compute the alignment for each frame and return
        # a vector of alignments
        nframes = R1_vector.shape[0]
        alignment=[]
        for i in range(0, nframes):

            # convert to unit vector
            V1 = R1_vector[i][0] / np.linalg.norm(R1_vector[i][0]) 
            V2 = R2_vector[i][0] / np.linalg.norm(R2_vector[i][0]) 

            # compute dot product and take arccos and do rad->deg to get angle
            # between the unit vectors
            alignment.append(np.rad2deg(np.arccos(np.dot(V1,V2))))
                
        return np.array(alignment)

    # ........................................................................
    #
    #
    def get_dihedral_mutual_information(self, angle_name='psi',  bwidth = np.pi/5.0, stride=1, weights=False):
        """
        Generate the full mutual information matrix for a specific diehdral
        type. The resulting matrix describes the mutual information between each 
        dihedral angle as defined by the variable angle_name. A weights parameter
        can be passed if frames are to be re-weighted, but this requires that
        the (number of frames) / stride = the number of weights. 

        The mutual information for a pair of angles is determined by generating
        a histogram of each dihedral induvidually (p(phi1), p(phi2)) and the joint 
        probability histogram (p(phi1,phi2)), and then computing the Shannon 
        entropy associated with the single and joing probability histograms (H_phi1, 
        H_phi2, H_phi1_phi2). The mutual information is then returned as

        H_phi1 + H_phi2 - (H_phi1 * H_phi2 )

        The easiest way to interpret these results is to normalize the inferred
        matrix using an equivalent matrix generated using a limiting polymer
        model (e.g. an EV or FRC simulation).

        Return:
        Mutual information matrix ( n x n) where n is the number of that type of
        bonds in the protein.
                       
        ........................................
        OPTIONS 
        ........................................

        angle_name
        String, must be one of the following options
        'chi1','phi, 'psi', 'omega'. 

        bwidth [np.array} {np.pi/5.0)
        The width of the bins that will stretch from -pi to pi. np.pi/5.0 is
        probablty the smallest binsize you want - even np.pi/2 should work
        well. You may want to experiment with this parameter...

        stride [int] {20}
        Defines the spacing between frames to compare - i.e. if comparing frame1 
        to a trajectory we'd compare frame 1 and every stride-th frame.

        weights [list or array of floats] {False}
        Defines the frame-specific weights if re-weighted analysis is required. This can be 
        useful if an ensemble has been re-weighted to better match experimental data, or in
        the case of analysing replica exchange data that is re-combined using T-WHAM.

        """

        
        ## ..................................................
        ## SAFETY FIRST!
        ##
        # verify binwidth input values
        if bwidth > 2*np.pi or not (bwidth > 0):
           raise CTException('The bwidth parameter must be between 2*pi and greater than 0')

        # if stride was passed make sure it's ok
        self.__check_stride(stride)

        # if weights were passed make sure they're LEGIT!
        weights = self.__check_weights(weights, stride)

        # check 
        ctutils.validate_keyword_option(angle_name, ['chi1', 'phi', 'psi', 'omega'], 'angle_name')

        ## ..................................................
        
        # define histogram bins based on passed bin width
        bins=np.arange(-np.pi, np.pi+bwidth, bwidth)
        
        # construct the selector dictionary
        selector = {"phi":md.compute_phi, "omega":md.compute_omega, "psi":md.compute_psi, "chi1":md.compute_chi1}

        # check the angle_name is an allowed name
        if angle_name not in list(selector.keys()):
            raise CTException('The variable angle_name was set to %s, which is not one of phi, omega, psi, chi1' % angle_name)            
        
        # select and compute the relevant angles of the subtrajectroy
        fx = selector[angle_name]
        angles = fx(self.traj[0::stride])
                            
        # construct empty matrices
        SIZE = len(angles[0])
        MI_mat = np.zeros((SIZE,SIZE))

        # populate matrices note we only compute the upper right triangle
        # but can populate the lower half because it's a symmetrical matrix
        for i in range(0,SIZE):
            for j in range(i,SIZE):

                X = np.transpose(angles[1])[j]
                Y = np.transpose(angles[1])[i]
                MI = ctmutualinformation.calc_MI(X,Y, bins, weights)

                MI_mat[i,j] = MI
                MI_mat[j,i] = MI

        return MI_mat
        

    # ........................................................................
    #
    #
    def get_local_to_global_correlation(self, mode='COM', n_cycles=100, max_num_pairs=10, stride=20, weights=False, verbose=True):
        """
        Method to analyze how well ensemble average distances taken from a finite number of inter-residue 
        distances correlate with global dimensions as measured by the radius of gyration. This is a new
        analysis, that is best explained through a formal write up.

        Parameters
        ----------
        mode : str {'COM'}
            Must be one of either 'CA' or 'COM'.

            - 'CA' = alpha carbon.
            - 'COM' = center of mass (associated withe the residue).
        
        n_cycles : int {100}
            Number of times, for each number of pairs, we re-select a different
            set of paris to use. This depends (weakly) on the number of residues,
            but we do not recommend a value < 50. For larger proteins this number
            should be increased. Again, it's worth examining how your results
            chain as a function of n_cycles to determine the optimal tradeoff
            between speed and precision.

        max_num_pairs : int {10}
            The maximum number of pairs to be consider for correlation analysis.
            In general we've found above 10-20 the average correlation tends to 
            plateau towards 1 (note it will NEVER be 1) so 1-20 is a reasonable
            set to use.

        stride : int {20}
            Defines the spacing between frames for calculating the ensemble
            average. As stride gets larger this analysis gets slower.
            It is worth experimenting with to see how the results change
            as a function of stride, but in theory the accuracy should
            remain fixed but precision improved as stride is reduced.

        weights : bool {False}
            Flag that indicates if frame weights should be used or not.

        verbose : bool
            Flag that by default is True determines if the function prints status updates. This is relevant because
            this function can be computationally expensive, so having some report on status can be comforting!

        Returns
        -------
        tuple
            Returns a four-place tuple. 
        
            - [0] = This is an 2 by (n_cycles*max_num_pairs) array, where the first column is the number 
              of pairs and the second column is the Rg-lambda correlation for a specific set of pairs (the 
              pairs in question are not included). This can be thought of as the 'raw' data, and may only 
              be useful if distributions of the correlation are of interest (e.g. for generating 2D histograms).

            - [1] = Array with the number of pairs used (e.g. if max_num_pairs = 10 then this would be
              [1,2,3,4,5,6,7,8,9]).

            - [2] = Array with the mean correlation associated with the numbers of pairs in position 2
              and the radius of gyration.
            
            - [3] = Array with the standard deviation of the correlation associated with the number of 
              pairs in position 2 and the radius of gyration. Note the inclusion of the standard 
              deviation makes the assumption that the distribution is Gaussian which may or may
              not be true.

        Raises
        ------
        CTException
            Raised when the mode is not 'CA' or 'COM'; or, when the lengths of the Rg-stride derived 
            calculations did not match the lengths of the internal distances; or, when the installed 
            numpy version doesn't support the `aweights` keyword for the `numpy.cov` function.
        """
        
        weights = self.__check_weights(weights, stride)
        

        ctutils.validate_keyword_option(mode, ['CA', 'COM'], 'mode')

        # note start and end here are after offset correction
        start = self.resid_with_CA[0] 
        end = self.resid_with_CA[-1]
    
        FIRST_CHECK = True

        # start with a sequence separation of 1
        for seq_sep in range(1, self.n_residues):
            ctio.status_message("On sequence separation %i" % (seq_sep), verbose) 

            for pos in range(start, end - seq_sep):

                # define the two positions
                A = pos
                B = pos + seq_sep
                
                # get the distance for every stride-th frame between those two positions using either the CA
                # mode or the COM mode
                if mode == 'CA':
                    distance = self.get_inter_residue_atomic_distance(A, B, stride=stride, correctOffset=False)

                elif mode == 'COM':
                    distance = self.get_inter_residue_COM_distance(A, B, stride=stride, correctOffset=False)

                if FIRST_CHECK:
                    all_distances = distance
                    FIRST_CHECK = False
                else:
                    all_distances = np.vstack((all_distances, distance))

                    
        full_rg = self.get_radius_of_gyration()
        stride_rg = full_rg[0::stride]

        if len(stride_rg) != len(all_distances[0]):
            raise CTException('Something when wrong when comparing stride-derived Rg and internal distances, this is a bug in the code...)') 

        # total number of distance pairs
        n_pairs = len(all_distances)

        pair_selection_vector = np.arange(1,max_num_pairs,1)
        
        return_data = np.zeros((len(pair_selection_vector)*n_cycles,2))

        weights = False
        weights = np.repeat(1.0/len(stride_rg),len(stride_rg))

        idx=0
        for n_selected in pair_selection_vector:
            ctio.status_message("On %i pairs selected" % n_selected, verbose)
            for i in range(0,n_cycles):

                # select n_select different values between 0 and n_pairs
                idx_selection = np.random.randint(0, n_pairs, n_selected)
                
                # this next line means that for each idx_selection value (i.e. for each pair of distances)
                # we calculate the squared value of each distance, then for each conformation SUM all the pairs
                # and then for each of those n_frame summs divide by 2 * n_selected squared
                # this gives a series of values for EACH conformation (so local mean is a 1xn_configurations vector)
                local_mean_square = np.sum(np.power(all_distances[idx_selection],2),0)/(2*(n_selected*n_selected))

                # correlation between local mean square and rg_square - returns a SINGLE value
                
                # THIS is the covariance matrix, but we can pass a weighting factor to this making it better suited for
                # weighted ensembles

                if weights is not False:
                    try:
                        cov_matrix = np.cov(np.vstack((local_mean_square, np.power(stride_rg,2))), ddof=0, aweights=weights)
                    except TypeError:
                        # this probaby happend because the version of numpy doesn't support aweights. If this is the case try again
                        # without weights assuming weights are equal
                        if len(set(weights)) == 1:
                            cov_matrix = np.cov(np.vstack((local_mean_square, np.power(stride_rg,2))))
                        else:
                            raise CTException('Weights being passed to get_global_from_local but the current version of numpy (%s) may not support weights via the "aweights" keyword...' % np.version.full_version)
                
                    # this computes the upper right square from the correlation matrix from the covariance matrix using (Rij = (Cij/(sqrt(Cii - Cjj))) where i and j are
                    # 0 and 1 respectively
                    c = cov_matrix[0,1]/(np.sqrt(cov_matrix[0,0]*cov_matrix[1,1]))
                else:
                    # this is the correlation matrix and was the old way of doing this
                    c = np.corrcoef(local_mean_square, np.power(stride_rg,2))[0][1]               
                                    
                return_data[idx] = [n_selected, c]
                idx=idx+1

        # leaving this here incase we want to re-introduce the 2D histogram information in later versions...
        # np.histogram2d(np.transpose(return_data)[0],np.transpose(return_data)[1], bins=[np.arange(1,n_pairs), np.arange(0,1,0.01)]))
                            
        return  (return_data, 
                 pair_selection_vector, 
                 np.mean(np.reshape(np.transpose(return_data)[1], (len(pair_selection_vector),n_cycles)),1), 
                 np.std(np.reshape(np.transpose(return_data)[1], (len(pair_selection_vector),n_cycles)),1))
        


    # ........................................................................
    #
    #
    def get_end_to_end_vs_rg_correlation(self, mode='COM'):
        """
        Computes the correlation between Rg^2 and end-to-end^2. 

        Parameters
        ---------

        mode: str {'CA'}
            String, must be one of either 'CA' or 'COM'.
            - 'CA' = alpha carbon.
            - 'COM' = center of mass (associated withe the residue).

        Returns
        -------
        float
            A single float describing the correlation (as calculated by np.corrcoef).

        """

        # validate the keyword 
        ctutils.validate_keyword_option(mode, ['CA', 'COM'], 'mode')

        # get end-to-end distance
        distance = self.get_end_to_end_distance(mode)            

        # get radius of gyration
        full_rg = self.get_radius_of_gyration()
                
        # NOTE this is the same as Re^2 =  RG^2/ 6 (standard Debye result for a Gaussian chain) - basically asking
        # about fractality more than a specific chain model, because examining correlation the scalar factor doesn't
        # matter , ie really this is Rg^2 vs Re^2 - scalar is irrelevant. But, this approach is consistent with
        # the approach in the get_local_to_global_correlation() function
        local_mean_square = np.power(distance,2)/(2)
        c = np.corrcoef(local_mean_square, np.power(full_rg,2))[0][1]                
                                            
        return c

    # ........................................................................
    #
    #
    def get_secondary_structure_DSSP(self, R1=None, R2=None, correctOffset=True):
        """
        Returns the a 4 by n numpy array inwhich column 1 gives residue number, column 2 is local helicity,  
        column 3 is local 'extended' (beta strand/sheet) and column 4 is local coil on a per-residue
        basis.

        Parameter R1 and R2 define a local region if only a sub-region is required.

        Return vector provides normalized secondary structure (between 0 and 1) which reflects
        the fraction of the simulation each residue is in that particular secondary structure type.

        Parameters
        ----------

        R1 : int {None}
             Default value is None. Defines the value for first residue in the region of 
             interest. If not provided (False) then first residue is used.
              

        R2 : int {None}
             Default value is None. Defines the value for last residue in the region of 
             interest. If not provided (False) then last residue is used.
             
        correctOffset : Bool
             Defines if we perform local protein offset correction or not. By default we do, 
             but some internal functions may have already performed the correction and so don't
             need to perform it again. If you're calling this function you can probably ignore
             this variable.


        Returns
        -------
        
        ddsp_vector : np.array
             A 4xn numpy array (where n is the number of residues) in which column 1 defines the
             residue index and column 2-4 defines the fractional occupancy of helical (H), 
             extended (E) (beta-like) and coil (C) states. Note the three classifications will
             sum to 1 (within numerical precision).
               
        """

        # build R1/R2 values
        out = self.__get_first_and_last(R1, R2, withCA=True)
        R1_real = out[0]
        R2_real = out[1]

        # select the relevant subtrajectory (out[2] is the 'resid %i to %i' where %i and %i are R1 and R2)
        ats = self.traj.atom_slice(self.topology.select('%s' % out[2]))

        # compute DSSP over the selected subtrajectory 
        dssp_data = md.compute_dssp(ats)
                
        C_vector = []
        E_vector = []
        H_vector = []

        # note the + 1 because the R1 and R2 positions are INCLUSIVE whereas  
        reslist    = list(range(R1_real, R2_real+1))
        n_frames   = self.n_frames
        
        for i in range(len(reslist)):
            C_vector.append(float(sum(dssp_data.transpose()[i] == 'C'))/n_frames)
            E_vector.append(float(sum(dssp_data.transpose()[i] == 'E'))/n_frames)
            H_vector.append(float(sum(dssp_data.transpose()[i] == 'H'))/n_frames)
                

        return np.array((reslist, H_vector, E_vector, C_vector))


    # ........................................................................
    #
    #
    def get_secondary_structure_BBSEG(self, R1=None, R2=None, correctOffset=True):
        """      
        Returns a dictionary where eack key-value pair is keyed by a BBSEG classification
        type (0-9) and each value is a vector showing the fraction of time each residue
        is in that particular BBSEG type.

        BBSEG classification types are listed below

        0 - unclassified
        1 - beta (turn/sheet)
        2 - PII (polyproline type II helix)
        3 - Unusual region
        4 - Right handed alpha helix
        5 - Inverse C7 Equatorial (gamma-prime turn)
        6 - Classic C7 Equatorial  (gamma turn)
        7 - Helix with 7 Residues per Turn
        8 - Left handed alpha helix
        
        Parameters R1 and R2 are optional and allow a local sub-region to be defined.

        The return dictionary provides a classification vector for each of the 9 possible
        types of classification (note 0 = unclassified).

        
        Parameters
        ----------

        R1 : int 
             Default value is False. Defines the value for first residue in the region of 
             interest. If not provided (False) then first residue is used.
              

        R2 : int
             Default value is False. Defines the value for last residue in the region of 
             interest. If not provided (False) then last residue is used.
             

        correctOffset : Bool
             Defines if we perform local protein offset correction or not. By default we do, 
             but some internal functions may have already performed the correction and so don't
             need to perform it again. If you're calling this function you can probably ignore
             this variable.

        Returns
        -------
        
        return_bbseg : dict
             Dictionary of 9 key-value pairs where keys are integers 0-8 and values are 
             numpy arrays showing the fractional occupancy of each of the distinct types 
             of defined secondary structure. Note the three classifications will sum to
             1 (within numerical precision).

        """

        # build R1/R2 values
        out = self.__get_first_and_last(R1, R2, withCA=True)

        # extract the phi/psi angles in degrees
        phi_data = np.degrees(md.compute_phi(self.traj.atom_slice(self.topology.select('%s'%(out[2]))))[1])
        psi_data = np.degrees(md.compute_psi(self.traj.atom_slice(self.topology.select('%s'%(out[2]))))[1])

        # extract the relevant information (note shape of phi_data and psi_data will be identical)
        # shape info here is (number_of_frames, number_of_residues) sized
        shape_info = np.shape(phi_data)
        all_classes = []

        # for each frame iterate through and classify each residue, building a shape_info
        # sized matrix where each elements reflects the BBSEG classification of that residue
        # in a given frame
        for f in range(0, shape_info[0]):

            # so each step through the loop we're passing two vectors, each of which 
            # is nres residues long
            all_classes.append(self.__phi_psi_bbseg(phi_data[f], psi_data[f]))

        # convert to a numpy array
        all_classes = np.array(all_classes)

        # finally cycle through each BBSEG classification type and average 
        # over each frame (shape_info[0] is number of frames)
        return_bbseg = {}
        for c in range(0,9):
            return_bbseg[c] = list(np.sum((all_classes == c)*1,0)/shape_info[0])

        return return_bbseg
     
   
    # ........................................................................
    #
    def __phi_psi_bbseg(self, phi_vector, psi_vector):
        """
        Internal function that takes two equally-matched phi and psi angle vectors and
        based on the pairwise combination classified each pair of elements using the
        BBSEG2 definition. Definition was generated from the BBSEG2 file distributed
        with CAMPARI, and is encoded and stored in the _internal_data module.

        NOTE that because this is an internal function we do not double check that the
        phi_vector and psi_vectors are of the same length, but this is critical, so
        if this function is being called make sure this is true!

        Parameters
        ----------
        phi_vector :   iterable (list or numpy vector)
             ordered list of phi angles for a specific residue

        psi_vector :   iterable (list or numpy vector)
            ordered list of psu angles for a specific residue
         
        Returns
        -------

        classes : list
             A list of length equal to phi_vector and psi_vector that 
             classifies each pair of phi/psi angles using the BBSEG2
             definition.
        """

        classes = []

        for i in range(len(phi_vector)):
            phi = phi_vector[i]
            psi = psi_vector[i]

            fixed_phi = phi-(phi%10)
            fixed_psi = psi-(psi%10)

            # following corrections for edge cases if we hit 
            if fixed_phi == 180.0:
                fixed_phi = 170.0

            if fixed_psi == 180.0:
                fixed_psi = 170.0
                
            # classify the phi/psi values in terms of BBSEG values
            classes.append(BBSEG2[fixed_phi][fixed_psi])

        return classes

            
    # ........................................................................
    #
    def get_overlap_concentration(self):

        """
        Returns the overlap concentration for the chain.

        The overlap concentration reflects the concentration at which a flexible
        polymer begins to 'collide' in trans with other polymers - i.e. the 
        concentration at which the chains begin to overlap.

        Returns
        -------
        float 
            Molar concentration for the overlap concentration.
        """

        return ctpolymer.get_overlap_concentration(np.mean(self.get_radius_of_gyration()))
        
                    

    # ........................................................................
    #
    #
    def get_angle_decay(self, atom1='C', atom2='N', return_full_matrix=False):
                    
        """
        Returns the a 4 by n numpy array in which column 1 gives residue number, column 2 is local helicity,  

        No checking of atom1 and atom2...

        Parameters
        ----------

        atom1: str {C}
            The first atom to use when calculating the angle decay.

        atom2: str {N}
            The second atom to use when calculating the angle decay.

        return_full_matrix: bool {False}
            Whether or not to return the full matrix along with the angle decay calculation.

        Returns
        -------
        array_like, or 2-tuple
            If `array_like`, the matrix returned is comprised of only the angle decay.
            If a 2-tuple, both the angle decay matrix (index 0) and the full matrix is returned (index 1). 
        """

        # first compute all the C-N vector for each residue

        CN_vectors = []
        CN_lengths = [] 
        for i in self.resid_with_CA:

            # this extracts the C->N vector for each frame for each residue
            value = np.squeeze(self.traj.atom_slice(self.__residue_atom_lookup(i, atom1)).xyz) - np.squeeze(self.traj.atom_slice(self.__residue_atom_lookup(i, atom2)).xyz)

            # CN_vectors becomes a list where each element is [3 x nframes] array where 3 is the x/y/z vector coordinates
            CN_vectors.append(value)

            # CN_lengths extracts the ||v|| length of each vector (should be basically the same)
            CN_lengths.append(np.linalg.norm(value,axis=1))

        # calculate the number of residues for which we have C->N vectors 
        npos = len(CN_vectors)

        # initialize an empty dictionary - the keys for this are i-j sequence separation, 
        # and values are the cos(theta) angle between pairs of vectors
        all_vals={}
        for i in range(1, npos):
            all_vals[i] = []

        # precompute 
        length_multiplier = {}
        for i1 in range(0, npos-1):
            length_multiplier[i1] = {}
            for j1 in range(i1+1, npos):
                length_multiplier[i1][j1] = CN_lengths[i1]*CN_lengths[j1]
                        
        # we then cycle over the non-redudant set of pairwise residues in the protein
        for i1 in range(0, npos-1):
            for j1 in range(i1+1, npos):

                # for each frame calculate (u . v) / (||u|| * ||v||)
                # where u and v are vectors and "." is the dot product between each pair. We're only calculating PAIR-WISE dot product
                # of each [x,y,z] with [x,y,z] vector, so doing np.sum(Matrix*matrix) is SO SO SO much faster than anything else. We 
                # also take the average to avoid storing a ton of numbers and generating these giant vectors
                    
                all_vals[j1-i1].append(np.mean(np.sum(CN_vectors[i1]*CN_vectors[j1],axis=1)/length_multiplier[i1][j1]))

        return_matrix = []
        return_matrix.append([0,1.0,0.0])
        for k in all_vals:
            return_matrix.append([k, np.mean(all_vals[k]), np.std(all_vals[k])])
             
        # if we want the nres by nres matrix with specific decay <cos(omega)> for each specific pairwise
        # residue-residue set
        if return_full_matrix:

            full_matrix = np.zeros((len(return_matrix),len(return_matrix)))

            # for 0 to the number of residues (i.e. each row in the [nres x nres] matrix
            for i in range(0, len(return_matrix)):

                # set the column selector (c) to zero
                c = 0
                # iterate through 
                for j in range(0, len(all_vals[i])):
                    full_matrix[i,c] = all_vals[i][j]

                for j in range(len(all_vals[i]), len(return_matrix)):
                    full_matrix[i,c] = 0.0

            return (return_matrix, full_matrix)
        else:
            return return_matrix
        


    #oxoxoxoxoxooxoxoxoxoxoxoxoxoxoxoxooxoxoxoxoxoxoxoxoxoxoxooxoxoxoxoxoxoxoxoxoxoxooxoxo
    #
    #
    def get_local_collapse(self, window_size=10, bins=None, verbose=True):
        """        


        local collapse calculates a vectorial representation of the radius of gyration along a
        polypeptide chain. This makes it very easy to determine where you see local collapse 
        vs. local expansion.
                
        Parameters
        ----------

        window_size : int, default=10
            Size of the window over which conformations are examined. Default is 10.

        bins : np.arange or list
            A range of values (np.arange or list) spanning histogram bins. Default is np.arange(0, 10, 0.1).

        verbose : bool
            Flag that by default is True determines if the function prints status updates. This is relevant because
            this function can be computationally expensive, so having some report on status can be comforting!


        Returns
        -------
        tuple (len = 4)

            return[0]  : list of floats of len *n*, where each float reports on the mean local collapse  a specific 
                         position along the sequence as defined by the fragment_size

            return[1]  : list of floats of len *n* , where each float reports on the standard deviation of the 
                         local collapse at a specific position along the sequence as defined by the fragment_size

            return[2]  : List of np.ndarrays of len *n*, where each sub-array reports on the histogram values associated
                         with the local collapse at a given position along the sequence

            return[3]  : np.ndarray which corresponds to bin values for each of the histograms in return[2]

        """
        # validate bins
        if bins is None:
            bins = np.arange(0,10,0.01)
        else:
            try:
                if len(bins)  < 2:
                    raise CTException('Bins should be a numpy defined vector of values - e.g. np.arange(0,1,0.01)')                    
            except TypeError:
                raise CTException('Bins should be a list, vector, or numpy array of evenly spaced values')

            try:
                bins = np.array(bins, dtype=float)
            except ValueError:
                raise CTException('Passed bins could not be converted to a numpy array of floats')

        n_residues = self.n_residues
        n_frames   = self.n_frames

        # check the window is an appropriate size
        if window_size > n_residues:
            raise CTException('window_size is larger than the number of residues')
        
        meanData = []
        stdData  = []
        histo    = []                             
        
        for i in range(window_size - 1, n_residues):
                    
            ctutils.status_message("On range %i" % i, verbose)

            # get radius of gyration (now by default is in Angstroms
            # - in previous versions we performed a conversion here)
            tmp = self.get_radius_of_gyration(i - (window_size-1), i)
                

            (b, c) = np.histogram(tmp, bins)
            histo.append(b)
                                
            meanData.append(np.mean(tmp))
            stdData.append(np.std(tmp))


        return (meanData, stdData, histo, bins)


        



        
        

        

