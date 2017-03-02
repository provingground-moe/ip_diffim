from __future__ import absolute_import, division, print_function
from future import standard_library
standard_library.install_aliases()
#
# LSST Data Management System
# Copyright 2016 AURA/LSST.
#
# This product includes software developed by the
# LSST Project (http://www.lsst.org/).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the LSST License Statement and
# the GNU General Public License along with this program.  If not,
# see <https://www.lsstcorp.org/LegalNotices/>.
#

import numpy as np
import abc
from future.utils import with_metaclass

import lsst.afw.image as afwImage
import lsst.afw.math as afwMath
import lsst.afw.geom as afwGeom
import lsst.pex.config as pexConfig
import lsst.pipe.base as pipeBase

__all__ = ("ImageMapReduceTask", "ImageMapReduceConfig",
           "ImageMapperSubtask", "ImageMapperSubtaskConfig",
           "ImageReducerSubtask", "ImageReducerSubtaskConfig")


class ImageMapperSubtaskConfig(pexConfig.Config):
    """Configuration parameters for ImageMapperSubtask
    """
    pass


class ImageMapperSubtask(with_metaclass(abc.ABCMeta, pipeBase.Task)):
    """Abstract base class for any task that is to be
    used as `ImageMapReduceConfig.mapperSubtask`.

    An `ImageMapperSubtask` is responsible for processing individual
    sub-exposures in its `run` method, which is called from
    `ImageMapReduceTask.run`. `run` may return a processed new
    sub-exposure which can be be "stitched" back into a new resulting
    larger exposure (depending on the configured
    `ImageReducerSubtask`); otherwise if it does not return an
    afw.Exposure, then the
    `ImageReducerSubtask.config.reducerSubtask.reduceOperation`
    should be set to 'none' and the result will be propagated
    as-is.
    """
    ConfigClass = ImageMapperSubtaskConfig
    _DefaultName = "ip_diffim_ImageMapperSubtask"

    @abc.abstractmethod
    def run(self, subExposure, expandedSubExposure, fullBBox, **kwargs):
        """Perform operation on given `subExposure`.

        To be implemented by subclasses. See class docstring for more
        details. This method is given the `subExposure` which
        is to be operated upon, and an `expandedSubExposure` which
        will contain `subExposure` with additional surrounding
        pixels. This allows for, for example, convolutions (which
        should be performed on `expandedSubExposure`), to prevent the
        returned sub-exposure from containing invalid pixels.

        This method may return a new, processed sub-exposure which can
        be be "stitched" back into a new resulting larger exposure
        (depending on the paired, configured `ImageReducerSubtask`);
        otherwise if it does not return an afw.Exposure, then the
        `ImageReducerSubtask.config.mapperSubtask.reduceOperation`
        should be set to 'none' and the result will be propagated
        as-is.

        Parameters
        ----------
        subExposure : afw.Exposure
            the sub-exposure upon which to operate
        expandedSubExposure : afw.Exposure
            the expanded sub-exposure upon which to operate
        fullBBox : afwGeom.BoundingBox
            the bounding box of the original exposure
        kwargs :
            additional keyword arguments propagated from
            `ImageMapReduceTask.run`.

        Returns
        -------
        A `pipeBase.Struct containing the result of the `subExposure` processing,
        which may itself be of any type. See above for details. If it is an
        afwImage.Exposure (processed sub-exposure), then the name in the Struct
        should be 'subExposure'. This is implemented here as an example only.
        """
        return pipeBase.Struct(subExposure=subExposure)


class ImageReducerSubtaskConfig(pexConfig.Config):
    """Configuration parameters for the ImageReducerSubtask
    """
    reduceOperation = pexConfig.ChoiceField(
        dtype=str,
        doc="""Operation to use for reducing subimages into new image.""",
        default="average",
        allowed={
            "none": """simply return a list of values and don't re-map results into
                       a new image (noop operation)""",
            "copy": """copy pixels directly from subimage into correct location in
                       new exposure (potentially non-deterministic for overlaps)""",
            "sum": """add pixels from overlaps (probably never wanted; used for testing)
                       into correct location in new exposure""",
            "average": """same as copy, but also average pixels from overlapped regions
                       (NaNs ignored)"""
        }
    )


class ImageReducerSubtask(pipeBase.Task):
    """Base class for any task that is to be
    used as `ImageMapReduceConfig.reducerSubtask`.

    Basic reduce operations are provided by the `run` method
    of this class, to be selected by its config.
    """
    ConfigClass = ImageReducerSubtaskConfig
    _DefaultName = "ip_diffim_ImageReducerSubtask"

    def run(self, mapperResults, exposure, **kwargs):
        """Reduce a list of items produced by `ImageMapperSubtask`.

        If `self.config.reduceOperation` is not 'none', then expect
        that the `pipeBase.Struct`s in the `mapperResults` list
        contain sub-exposures named 'subExposure', to be stitched back
        into a single Exposure with the same dimensions, PSF, and mask
        as the input `exposure`. Otherwise, the `mapperResults` list
        is simply returned directly.

        Parameters
        ----------
        mapperResults : list
            list of `pipeBase.Struct` returned by `ImageMapperSubtask.run`.
        exposure : afwImage.Exposure
            the original exposure which is cloned to use as the
            basis for the resulting exposure (if
            self.config.mapperSubtask.reduceOperation is not 'none')
        kwargs :
            additional keyword arguments propagaged from
            `ImageMapReduceTask.run`.

        Returns
        -------
        A `pipeBase.Struct` containing either an `afw.Exposure` (named 'exposure')
        or a list (named 'result'), depending on `config.reduceOperation`.

        Notes
        -----
        And currently known issues:
        1. This currently should correctly handle overlapping sub-exposures.
           For overlapping sub-exposures, use `config.reduceOperation='average'`.
        2. This currently does not correctly handle varying PSFs (in fact,
           it just copies over the PSF from the original exposure)
        3. To be done: correct handling of masks as well.
        4. This logic currently makes *two* copies of the original exposure
           (one here and one in `mapperSubtask.run()`). Possibly of concern
           for large images on memory-constrained systems.
        """
        # No-op; simply pass mapperResults directly to ImageMapReduceTask.run
        if self.config.reduceOperation == 'none':
            return pipeBase.Struct(result=mapperResults)

        newExp = exposure.clone()
        newMI = newExp.getMaskedImage()

        reduceOp = self.config.reduceOperation
        if reduceOp == 'copy':
            newMI.getImage()[:, :] = np.nan
            newMI.getVariance()[:, :] = np.nan
        else:
            newMI.getImage()[:, :] = 0.
            newMI.getVariance()[:, :] = 0.
            if reduceOp == 'average':  # make an array to keep track of weights
                weights = afwImage.ImageF(newMI.getBBox())  # must be a float to divide later.

        for item in mapperResults:
            item = item.subExposure  # Expected named value in the pipeBase.Struct
            if not (isinstance(item, afwImage.ExposureF) or isinstance(item, afwImage.ExposureI) or
                    isinstance(item, afwImage.ExposureU) or isinstance(item, afwImage.ExposureD)):
                raise TypeError("""Expecting an Exposure type, got %s.
                                   Consider using `reduceOperation="none".""" % str(type(item)))
            subExp = afwImage.ExposureF(newExp, item.getBBox())
            subMI = subExp.getMaskedImage()
            patchMI = item.getMaskedImage()
            isNan = (np.isnan(patchMI.getImage().getArray()) |
                     np.isnan(patchMI.getVariance().getArray()))
            noNans = np.sum(isNan) <= 0
            if reduceOp == 'copy':
                if noNans:
                    subMI[:, :] = patchMI
                else:
                    isNotNan = ~isNan
                    subMI.getImage().getArray()[isNotNan] = patchMI.getImage().getArray()[isNotNan]
                    subMI.getVariance().getArray()[isNotNan] = patchMI.getVariance().getArray()[isNotNan]
            if reduceOp == 'sum' or reduceOp == 'average':  # much of these two options is the same
                if noNans:
                    subMI += patchMI
                    if reduceOp == 'average':
                        # wsubim is a view into the `weights` Image, so here we simply add one to
                        # the region of `weights` confined by `item.getBBox()`.
                        wsubim = afwImage.ImageF(weights, item.getBBox())
                        wsubim += 1.
                else:
                    isNotNan = ~isNan
                    subMI.getImage().getArray()[isNotNan] += patchMI.getImage().getArray()[isNotNan]
                    subMI.getVariance().getArray()[isNotNan] += patchMI.getVariance().getArray()[isNotNan]
                    if reduceOp == 'average':
                        wsubim = afwImage.ImageF(weights, item.getBBox())
                        wsubim.getArray()[isNotNan] += 1.

        if reduceOp == 'average':
            newMI /= weights

        return pipeBase.Struct(exposure=newExp)


class ImageMapReduceConfig(pexConfig.Config):
    """Configuration parameters for the ImageMapReduceTask
    """
    mapperSubtask = pexConfig.ConfigurableField(
        doc="Subtask to run on each subimage",
        target=ImageMapperSubtask,
    )

    reducerSubtask = pexConfig.ConfigurableField(
        doc="Subtask to combine results of mapperSubTask",
        target=ImageReducerSubtask,
    )

    # Separate gridCentroidsX and gridCentroidsY since pexConfig.ListField accepts limited dtypes
    #  (i.e., no Point2D). The resulting set of centroids is the "vertical stack" of
    #  `gridCentroidsX` and `gridCentroidsY`.
    gridCentroidsX = pexConfig.ListField(
        dtype=float,
        doc="""Input X centroids around which to place subimages.
               If None, use grid config options below.""",
        optional=True,
        default=None
    )

    gridCentroidsY = pexConfig.ListField(
        dtype=float,
        doc="""Input Y centroids around which to place subimages.
               If None, use grid config options below.""",
        optional=True,
        default=None
    )

    gridSizeX = pexConfig.Field(
        dtype=float,
        doc="""Dimensions of each grid cell in x direction""",
        default=10.,
        check=lambda x: x > 0.
    )

    gridSizeY = pexConfig.Field(
        dtype=float,
        doc="""Dimensions of each grid cell in y direction""",
        default=10.,
        check=lambda x: x > 0.
    )

    gridStepX = pexConfig.Field(
        dtype=float,
        doc="""Spacing between subsequent grid cells in x direction. If equal to
               gridSizeX, then there is no overlap in the x direction.""",
        default=10.,
        check=lambda x: x > 0.
    )

    gridStepY = pexConfig.Field(
        dtype=float,
        doc="""Spacing between subsequent grid cells in y direction. If equal to
               gridSizeY, then there is no overlap in the y direction.""",
        default=10.,
        check=lambda x: x > 0.
    )

    borderSizeX = pexConfig.Field(
        dtype=float,
        doc="""Dimensions of grid cell border in +/- x direction, to be used
               for generating `expandedSubExposure`.""",
        default=5.,
        check=lambda x: x > 0.
    )

    borderSizeY = pexConfig.Field(
        dtype=float,
        doc="""Dimensions of grid cell border in +/- y direction, to be used
               for generating `expandedSubExposure`.""",
        default=5.,
        check=lambda x: x > 0.
    )

    adjustGridOption = pexConfig.ChoiceField(
        dtype=str,
        doc="""Whether and how to adjust grid to fit evenly within, and cover entire
               image""",
        default="spacing",
        allowed={
            "spacing": "adjust spacing between centers of grid cells (allowing overlaps)",
            "size": "adjust the sizes of the grid cells (disallowing overlaps)",
            "none": "do not adjust the grid sizes or spacing"
        }
    )

    scaleByFwhm = pexConfig.Field(
        dtype=bool,
        doc="""Scale gridSize/gridStep/borderSize/overlapSize by PSF FWHM rather
               than pixels?""",
        default=True
    )

    ignoreMaskPlanes = pexConfig.ListField(
        dtype=str,
        doc="""Mask planes to ignore for sigma-clipped statistics""",
        default=("INTRP", "EDGE", "DETECTED", "SAT", "CR", "BAD", "NO_DATA", "DETECTED_NEGATIVE")
    )


## \addtogroup LSST_task_documentation
## \{
## \page ImageMapReduceTask
## \ref ImageMapReduceTask_ "ImageMapReduceTask"
##      Task for performing operations on an image over a regular-spaced grid
## \}


class ImageMapReduceTask(pipeBase.Task):
    """Split an Exposure into subExposures (optionally on a grid) and
    perform the same operation on each.

    Perform 'simple' operations on a gridded set of subExposures of a
    larger Exposure, and then (by default) have those subExposures
    stitched back together into a new, full-sized image.

    Contrary to the expectation given by its name, this task does not
    perform these operations in parallel, although it could be updatd
    to provide such functionality.

    The actual operations are performed by two subTasks passed to the
    config. The exposure passed to this task's `run` method will be
    divided, and those subExposures will be passed to the subTasks,
    along with the original exposure. The reducing operation is
    performed by the second subtask.
    """
    ConfigClass = ImageMapReduceConfig
    _DefaultName = "ip_diffim_imageMapReduce"

    def __init__(self, *args, **kwargs):
        """Create the image map-reduce task

        Parameters
        ----------
        args :
            arguments to be passed to
            `lsst.pipe.base.task.Task.__init__`
        kwargs :
            additional keyword arguments to be passed to
            `lsst.pipe.base.task.Task.__init__`
        """
        pipeBase.Task.__init__(self, *args, **kwargs)

        self.boxes0 = self.boxes1 = None
        self.makeSubtask("mapperSubtask")
        self.makeSubtask("reducerSubtask")

    @pipeBase.timeMethod
    def run(self, exposure, **kwargs):
        """Perform a map-reduce operation on the given exposure.

        Split the exposure into sub-expposures on a grid (parameters
        given by `ImageMapReduceConfig`) and perform
        `config.mapperSubtask.run()` on each. Reduce the resulting
        sub-exposures by running `config.reducerSubtask.run()`.

        Parameters
        ----------
        exposure : afwImage.ExposureF
            the full exposure to process
        kwargs :
            additional keyword arguments to be passed to
            subtask `run` methods

        Returns
        -------
        output of `reducerSubtask.run()`

        """
        mapperResults = self._runMapper(exposure, **kwargs)
        result = self._reduceImage(mapperResults, exposure, **kwargs)
        return result

    def _runMapper(self, exposure, doClone=False, **kwargs):
        """Perform `mapperSubtask.run` on each sub-exposure

        Perform `mapperSubtask.run` on each sub-exposure across a
        grid on `exposure` generated by `_generateGrid`. Also pass to
        `mapperSubtask.run` an 'expanded sub-exposure' containing the
        same region as the sub-exposure but with an expanded bounding box.

        Parameters
        ----------
        exposure : afwImage.ExposureF
            the original exposure which is used as the template
        doClone : boolean
            if True, clone the subimages before passing to subtask;
            in that case, the sub-exps do not have to be considered as read-only
        kwargs :
            additional keyword arguments to be passed to
            `mapperSubtask.run`

        Returns
        -------
        a list of `pipeBase.Struct`s as returned by `mapperSubtask.run`.
        """
        if self.boxes0 is None:
            self._generateGrid(exposure)
        if len(self.boxes0) != len(self.boxes1):
            raise ValueError('Bounding boxes list and expanded bounding boxes list are of different lengths')

        self.log.info("Processing %d sub-exposures", len(self.boxes0))
        mapperResults = []
        for box0, box1 in zip(self.boxes0, self.boxes1):
            subExp = afwImage.ExposureF(exposure, box0)
            expandedSubExp = afwImage.ExposureF(exposure, box1)
            if doClone:
                subExp = subExp.clone()
                expandedSubExp = expandedSubExp.clone()
            result = self.mapperSubtask.run(subExp, expandedSubExp, exposure.getBBox(), **kwargs)
            mapperResults.append(result)

        return mapperResults

    def _reduceImage(self, mapperResults, exposure, **kwargs):
        """Reduce/merge a set of sub-exposures into a final result

        Return an exposure of the same dimensions as `exposure`.
        `mapperResults` is expected to have been produced by `runMapper`.

        Parameters
        ----------
        mapperResults : list
            list of `pipeBase.Struct`, each of which was produced by
            `config.mapperSubtask`
        exposure : afwImage.Exposure
            the original exposure
        **kwargs :
            additional keyword arguments

        Returns
        -------
        Output of `reducerSubtask.run` which is a `pipeBase.Struct`.
        """
        result = self.reducerSubtask.run(mapperResults, exposure, **kwargs)
        return result

    def _generateGrid(self, exposure, forceEvenSized=False):
        """Generate two lists of bounding boxes that evenly grid `exposure`

        Unless the config was provided with `centroidCoordsX` and
        `centroidCoordsY`, grid (subimage) centers are spaced evenly
        by gridStepX/Y. Then the grid is adjusted as little as
        possible to evenly cover the input exposure (if
        adjustGridOption is not 'none'). Then the second set of
        bounding boxes is expanded by borderSizeX/Y. The expanded
        bounding boxes are adjusted to ensure that they intersect the
        exposure's bounding box. The resulting lists of bounding boxes
        and corresponding expanded bounding boxes are set to
        `self.boxes0`, `self.boxes1`.

        Parameters
        ----------
        exposure : `afwImage.Exposure`
            input exposure whose full bounding box is to be evenly gridded.
        forceEvenSized : boolean
            force grid elements to have even-valued x- and y- dimensions?
            (Potentially useful if doing Fourier transform of subExposures.)
        """
        # Extract the config parameters for conciseness.
        gridSizeX = self.config.gridSizeX
        gridSizeY = self.config.gridSizeY
        gridStepX = self.config.gridStepX
        gridStepY = self.config.gridStepY
        borderSizeX = self.config.borderSizeX
        borderSizeY = self.config.borderSizeY
        adjustGridOption = self.config.adjustGridOption
        scaleByFwhm = self.config.scaleByFwhm
        bbox = exposure.getBBox()

        psfFwhm = (exposure.getPsf().computeShape().getDeterminantRadius() *
                   2. * np.sqrt(2. * np.log(2.)))
        if scaleByFwhm:
            self.log.info("Scaling grid parameters by %f" % psfFwhm)

        def rescaleValue(val):
            if scaleByFwhm:
                return np.rint(val * psfFwhm).astype(int)
            else:
                return np.rint(val).astype(int)

        gridSizeX = rescaleValue(gridSizeX)
        if gridSizeX > bbox.getWidth():
            gridSizeX = bbox.getWidth()
        gridSizeY = rescaleValue(gridSizeY)
        if gridSizeY > bbox.getHeight():
            gridSizeY = bbox.getHeight()
        gridStepX = rescaleValue(gridStepX)
        if gridStepX > bbox.getWidth():
            gridStepX = bbox.getWidth()
        gridStepY = rescaleValue(gridStepY)
        if gridStepY > bbox.getHeight():
            gridStepY = bbox.getHeight()
        borderSizeX = rescaleValue(borderSizeX)
        borderSizeY = rescaleValue(borderSizeY)

        nGridX = bbox.getWidth() // gridStepX
        nGridY = bbox.getHeight() // gridStepY

        if adjustGridOption == 'spacing':
            nGridX = bbox.getWidth() / gridStepX
            # Readjust gridStepX so that it fits perfectly in the image.
            gridStepX = float(bbox.getWidth() - gridSizeX) / float(nGridX)
            if gridStepX < 1:
                raise ValueError('X grid spacing is too small (or negative): %f' % gridStepX)

        if adjustGridOption == 'spacing':
            nGridY = bbox.getWidth() / gridStepY
            # Readjust gridStepY so that it fits perfectly in the image.
            gridStepY = float(bbox.getHeight() - gridSizeY) / float(nGridY)
            if gridStepY < 1:
                raise ValueError('Y grid spacing is too small (or negative): %f' % gridStepY)

        if adjustGridOption == 'size':
            gridSizeX = gridStepX
            gridSizeY = gridStepY

        # first "main" box at 0,0
        bbox0 = afwGeom.Box2I(afwGeom.Point2I(bbox.getBegin()), afwGeom.Extent2I(gridSizeX, gridSizeY))
        # first expanded box
        bbox1 = afwGeom.Box2I(bbox0)
        bbox1.grow(afwGeom.Extent2I(borderSizeX, borderSizeY))

        self.boxes0 = []  # "main" boxes; store in task so can be extracted if needed
        self.boxes1 = []  # "expanded" boxes

        # use given centroids as centers for bounding boxes
        if self.config.gridCentroidsX is not None and len(self.config.gridCentroidsX) > 0:
            for i, centroidX in enumerate(self.config.gridCentroidsX):
                centroidY = self.config.gridCentroidsY[i]
                centroid = afwGeom.Point2D(centroidX, centroidY)
                bb0 = afwGeom.Box2I(bbox0)
                xoff = int(np.floor(centroid.getX())) - bb0.getWidth()//2
                yoff = int(np.floor(centroid.getY())) - bb0.getHeight()//2
                bb0.shift(afwGeom.Extent2I(xoff, yoff))
                bb0.clip(bbox)
                self.boxes0.append(bb0)
                bb1 = afwGeom.Box2I(bbox1)
                bb1.shift(afwGeom.Extent2I(xoff, yoff))
                bb1.clip(bbox)
                self.boxes1.append(bb1)
            return self.boxes0, self.boxes1

        def offsetAndClipBoxes(bbox0, bbox1, xoff, yoff, bbox):
            """Offset the "main" (bbox0) and "expanded" (bbox1) bboxes
            by xoff, yoff.

            Clip them by the exposure's bbox.
            """
            xoff = int(np.floor(xoff))
            yoff = int(np.floor(yoff))
            bb0 = afwGeom.Box2I(bbox0)
            bb0.shift(afwGeom.Extent2I(xoff, yoff))
            bb0.clip(bbox)
            bb1 = afwGeom.Box2I(bbox1)
            bb1.shift(afwGeom.Extent2I(xoff, yoff))
            bb1.clip(bbox)
            if forceEvenSized:
                bb0.grow(afwGeom.Extent2I(bb0.getWidth() % 2, bb0.getHeight() % 2))
                bb1.grow(afwGeom.Extent2I(bb1.getWidth() % 2, bb1.getHeight() % 2))
            return bb0, bb1

        xoff = 0
        while(xoff <= bbox.getWidth()):
            yoff = 0
            while(yoff <= bbox.getHeight()):
                bb0, bb1 = offsetAndClipBoxes(bbox0, bbox1, xoff, yoff, bbox)
                yoff += gridStepY
                if bb0.getArea() > 0 and bb1.getArea() > 0:
                    self.boxes0.append(bb0)
                    self.boxes1.append(bb1)
            xoff += gridStepX

    def _plotBoxes(self, exposure, skip=3):
        """Plot both grids of boxes using matplotlib.

        Will compute the grid via `_generateGrid` if
        `self.boxes0` and `self.boxes1` have not already been set.

        Parameters
        ----------
        exposure : afwImage.Exposure
            Exposure whose bounding box is gridded by this task.
        skip : int
            Plot every skip-ped box (help make plots less confusing)
        """
        import matplotlib.pyplot as plt

        bbox = exposure.getBBox()
        if self.boxes0 is None:
            self._generateGrid(exposure)
        self._plotBoxGrid(self.boxes0[::skip], bbox, ls='--')
        # reset the color cycle -- see
        # http://stackoverflow.com/questions/24193174/reset-color-cycle-in-matplotlib
        plt.gca().set_prop_cycle(None)
        self._plotBoxGrid(self.boxes1[::skip], bbox, ls=':')

    def _plotBoxGrid(self, boxes, bbox, **kwargs):
        """Plot a grid of boxes using matplotlib.

        Parameters
        ----------
        boxes : list
            a list of `afwGeom.BoundingBox`es
        bbox : afwGeom.BoundingBox
            an overall bounding box
        **kwargs :
            additional keyword arguments for matplotlib
        """
        import matplotlib.pyplot as plt

        def plotBox(box):
            corners = np.array([np.array([pt.getX(), pt.getY()]) for pt in box.getCorners()])
            corners = np.vstack([corners, corners[0, :]])
            plt.plot(corners[:, 0], corners[:, 1], **kwargs)

        for b in boxes:
            plotBox(b)
        plt.xlim(bbox.getBeginX(), bbox.getEndX())
        plt.ylim(bbox.getBeginY(), bbox.getEndY())
