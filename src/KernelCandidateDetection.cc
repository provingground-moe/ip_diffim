// -*- lsst-c++ -*-
/**
 * @file
 *
 * @brief Implementation of KernelCandidateDetection class
 *
 * @author Andrew Becker, University of Washington
 *
 * @ingroup ip_diffim
 */

#include "lsst/afw/geom.h"
#include "lsst/afw/image.h"
#include "lsst/afw/detection.h"
#include "lsst/log/Log.h"
#include "lsst/pex/exceptions/Exception.h"
#include "lsst/pex/policy/Policy.h"

#include "lsst/ip/diffim/FindSetBits.h"
#include "lsst/ip/diffim/KernelCandidateDetection.h"

namespace afwGeom   = lsst::afw::geom;
namespace afwImage  = lsst::afw::image;
namespace afwDetect = lsst::afw::detection;
namespace pexExcept = lsst::pex::exceptions;

namespace lsst {
namespace ip {
namespace diffim {


    template <typename PixelT>
    KernelCandidateDetection<PixelT>::KernelCandidateDetection(
        lsst::pex::policy::Policy const& policy
        ) :
        _policy(policy),
        _badBitMask(0),
        _footprints(std::vector<std::shared_ptr<lsst::afw::detection::Footprint>>()) {

        std::vector<std::string> detBadMaskPlanes = _policy.getStringArray("badMaskPlanes");
        for (std::vector<std::string>::iterator mi = detBadMaskPlanes.begin();
             mi != detBadMaskPlanes.end(); ++mi){
            try {
                _badBitMask |= afwImage::Mask<afwImage::MaskPixel>::getPlaneBitMask(*mi);
            } catch (pexExcept::Exception& e) {
                LOGL_DEBUG("TRACE3.ip.diffim.KernelCandidateDetection",
                           "Cannot update bad bit mask with %s", (*mi).c_str());
                LOGL_DEBUG("TRACE4.ip.diffim.KernelCandidateDetection",
                           e.what());
            }
        }
        LOGL_DEBUG("TRACE2.ip.diffim.KernelCandidateDetection",
                   "Using bad bit mask %d", _badBitMask);
    }



    /**
     * @brief Runs Detection on a single image for significant peaks, and checks
     * returned Footprints for Masked pixels.
     *
     * @note Accepts two MaskedImages, one of which is to be convolved to match the
     * other.  The Detection package is run on either the image to be convolved
     * (assumed to be higher S/N than the other image), or the image to not be
     * convolved (assumed lower S/N; however if you run detection on a very deep
     * template, you might not have significant S/N objects in the science image).
     * The subimages associated with each returned Footprint in both images are
     * checked for Masked pixels; Footprints containing Masked pixels are rejected.
     * The Footprints are grown by an amount specified in the Policy.  The
     * acceptible Footprints are returned in a vector.
     *
     * @return Vector of "clean" Footprints around which Image Subtraction
     * Kernels will be built.
     *
     */
    template <typename PixelT>
    void KernelCandidateDetection<PixelT>::apply(
        MaskedImagePtr const& templateMaskedImage,
        MaskedImagePtr const& scienceMaskedImage
        ) {

        // Parse the Policy
        int fpNpixMin                = _policy.getInt("fpNpixMin");
        int fpGrowPix                = _policy.getInt("fpGrowPix");

        bool detOnTemplate           = _policy.getBool("detOnTemplate");
        double detThreshold          = _policy.getDouble("detThreshold");
        std::string detThresholdType = _policy.getString("detThresholdType");

        /* reset private variables */
        _footprints.clear();

        // List of Footprints
        std::shared_ptr<std::vector<std::shared_ptr<afwDetect::Footprint>>> footprintListInPtr;

        // Find detections
        afwDetect::Threshold threshold =
            afwDetect::createThreshold(detThreshold, detThresholdType);

        if (detOnTemplate == true) {
            afwDetect::FootprintSet footprintSet(
                *(templateMaskedImage),
                threshold,
                "",
                fpNpixMin);
            // Get the associated footprints

            footprintListInPtr = footprintSet.getFootprints();
            LOGL_DEBUG("TRACE2.ip.diffim.KernelCandidateDetection.apply",
                       "Found %d total footprints in template above %.3f %s",
                       footprintListInPtr->size(), detThreshold, detThresholdType.c_str());
        }
        else {
            afwDetect::FootprintSet footprintSet(
                *(scienceMaskedImage),
                threshold,
                "",
                fpNpixMin);

            footprintListInPtr = footprintSet.getFootprints();
            LOGL_DEBUG("TRACE2.ip.diffim.KernelCandidateDetection.apply",
                       "Found %d total footprints in science image above %.3f %s",
                       footprintListInPtr->size(), detThreshold, detThresholdType.c_str());
        }

        // Iterate over footprints, look for "good" ones
        for (std::vector<std::shared_ptr<afwDetect::Footprint>>::iterator i = footprintListInPtr->begin();
             i != footprintListInPtr->end(); ++i) {

            growCandidate((*i), fpGrowPix, templateMaskedImage, scienceMaskedImage);
        }

        if (_footprints.size() == 0) {
            throw LSST_EXCEPT(pexExcept::Exception,
                              "Unable to find any footprints for Psf matching");
        }

        LOGL_DEBUG("TRACE1.ip.diffim.KernelCandidateDetection.apply",
                   "Found %d clean footprints above threshold %.3f",
                   _footprints.size(), detThreshold);

    }

    template <typename PixelT>
    bool KernelCandidateDetection<PixelT>::growCandidate(
        std::shared_ptr<lsst::afw::detection::Footprint> fp,
        int fpGrowPix,
        MaskedImagePtr const& templateMaskedImage,
        MaskedImagePtr const& scienceMaskedImage
        ) {
        int fpNpixMax = _policy.getInt("fpNpixMax");

        /* Functor to search through the images for masked pixels within *
         * candidate footprints.  Might want to consider changing the default
         * mask planes it looks through.
         */
        FindSetBits<afwImage::Mask<afwImage::MaskPixel> > fsb;

        afwGeom::Box2I fpBBox = fp->getBBox();
        /* Failure Condition 1)
         *
         * Footprint has too many pixels off the bat.  We don't want to throw
         * away these guys, they have alot of signal!  Lets just use the core of
         * it.
         *
         */
        if (fp->getArea() > static_cast<std::size_t>(fpNpixMax)) {
            LOGL_DEBUG("TRACE3.ip.diffim.KernelCandidateDetection.apply",
                       "Footprint has too many pix: %d (max =%d)",
                       fp->getArea(), fpNpixMax);

            int xc = int(0.5 * (fpBBox.getMinX() + fpBBox.getMaxX()));
            int yc = int(0.5 * (fpBBox.getMinY() + fpBBox.getMaxY()));
            std::shared_ptr<afwDetect::Footprint> fpCore(
                new afwDetect::Footprint(
                    std::make_shared<afwGeom::SpanSet>(afwGeom::Box2I(afwGeom::Point2I(xc, yc),
                                                       afwGeom::Extent2I(1,1))))
                );
            return growCandidate(fpCore, fpGrowPix, templateMaskedImage, scienceMaskedImage);
        }

        LOGL_DEBUG("TRACE5.ip.diffim.KernelCandidateDetection.apply",
                          "Original footprint in parent : %d,%d -> %d,%d -> %d,%d",
                          fpBBox.getMinX(), fpBBox.getMinY(),
                          int(0.5 * (fpBBox.getMinX() + fpBBox.getMaxX())),
                          int(0.5 * (fpBBox.getMinY() + fpBBox.getMaxY())),
                          fpBBox.getMaxX(), fpBBox.getMaxY());

        /* Grow the footprint
         * flag true  = isotropic grow   = slow
         * flag false = 'manhattan grow' = fast
         *
         * The manhattan masks are rotated 45 degree w.r.t. the coordinate
         * system.  They intersect the vertices of the rectangle that would
         * connect pixels (X0,Y0) (X1,Y0), (X0,Y1), (X1,Y1).
         *
         * The isotropic masks do take considerably longer to grow and are
         * basically elliptical.  X0, X1, Y0, Y1 delimit the extent of the
         * ellipse.
         *
         * In both cases, since the masks aren't rectangles oriented with
         * the image coordinate system, when we DO extract such rectangles
         * as subimages for kernel fitting, some corner pixels can be found
         * in multiple subimages.
         *
         */
        std::shared_ptr<afwDetect::Footprint> fpGrow = std::make_shared<afwDetect::Footprint>(
            fp->getSpans()->dilated(fpGrowPix, afwGeom::Stencil::MANHATTAN)
        );

        /* Next we look at the image within this Footprint.
         */
        afwGeom::Box2I fpGrowBBox = fpGrow->getBBox();
        LOGL_DEBUG("TRACE5.ip.diffim.KernelCandidateDetection.apply",
                   "Grown footprint in parent : %d,%d -> %d,%d -> %d,%d",
                   fpGrowBBox.getMinX(), fpGrowBBox.getMinY(),
                   int(0.5 * (fpGrowBBox.getMinX() + fpGrowBBox.getMaxX())),
                   int(0.5 * (fpGrowBBox.getMinY() + fpGrowBBox.getMaxY())),
                   fpGrowBBox.getMaxX(), fpGrowBBox.getMaxY());

        /* Failure Condition 2)
         * Grown off the image
         */
        if (!(templateMaskedImage->getBBox().contains(fpGrowBBox))) {
            LOGL_DEBUG("TRACE3.ip.diffim.KernelCandidateDetection.apply",
                       "Footprint grown off image");
            return false;
        }

        /* Grab subimages; report any exception */
        bool subimageHasFailed = false;
        try {
            afwImage::MaskedImage<PixelT> templateSubimage(*templateMaskedImage, fpGrowBBox);
            afwImage::MaskedImage<PixelT> scienceSubimage(*scienceMaskedImage, fpGrowBBox);

            // Search for any masked pixels within the footprint
            fsb.apply(*(templateSubimage.getMask()));
            if (fsb.getBits() & _badBitMask) {
                LOGL_DEBUG("TRACE3.ip.diffim.KernelCandidateDetection.apply",
                           "Footprint has masked pix (vals=%d) in image to convolve",
                           fsb.getBits());
                subimageHasFailed = true;
            }

            fsb.apply(*(scienceSubimage.getMask()));
            if (fsb.getBits() & _badBitMask) {
                LOGL_DEBUG("TRACE3.ip.diffim.KernelCandidateDetection.apply",
                           "Footprint has masked pix (vals=%d) in image not to convolve",
                           fsb.getBits());
                subimageHasFailed = true;
            }

        } catch (pexExcept::Exception& e) {
            LOGL_DEBUG("TRACE3.ip.diffim.KernelCandidateDetection.apply",
                       "Exception caught extracting Footprint");
            LOGL_DEBUG("TRACE4.ip.diffim.KernelCandidateDetection.apply",
                       e.what());
            subimageHasFailed = true;
        }
        if (subimageHasFailed) {
            return false;
        } else {
            /* We have a good candidate */
            _footprints.push_back(fpGrow);
            return true;
        }
    }

/***********************************************************************************************************/
//
// Explicit instantiations
//
    typedef float PixelT;
    template class KernelCandidateDetection<PixelT>;

}}} // end of namespace lsst::ip::diffim
